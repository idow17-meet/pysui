#    Copyright Frank V. Castellucci
#    SPDX-License-Identifier: Apache-2.0

# -*- coding: utf-8 -*-

"""Sui Configuration Group."""

import base64
import hashlib
import dataclasses
from typing import Optional, Union
import dataclasses_json
from pysui.abstracts.client_keypair import SignatureScheme
import pysui.sui.sui_crypto as crypto
import pysui.sui.sui_utils as utils
from pysui.sui.sui_constants import SUI_MAX_ALIAS_LEN, SUI_MIN_ALIAS_LEN


@dataclasses.dataclass
class ProfileAlias(dataclasses_json.DataClassJsonMixin):
    """Holds alias for base64 public key."""

    alias: str
    public_key_base64: str


@dataclasses.dataclass
class ProfileKey(dataclasses_json.DataClassJsonMixin):
    """Holds private key base64 string."""

    private_key_base64: str


@dataclasses.dataclass
class Profile(dataclasses_json.DataClassJsonMixin):
    """Unique connection profile."""

    profile_name: str  # Known as environmental alias in sui configuration
    url: str
    faucet_url: Optional[str] = None
    faucet_status_url: Optional[str] = None


@dataclasses.dataclass
class ProfileGroup(dataclasses_json.DataClassJsonMixin):
    """Represents a group of profile."""

    group_name: str
    using_profile: str
    using_address: str
    alias_list: list[ProfileAlias]
    key_list: list[ProfileKey]
    address_list: Optional[list[str]] = dataclasses.field(default_factory=list)
    profiles: Optional[list[Profile]] = dataclasses.field(default_factory=list)

    def _profile_exists(self, *, profile_name: str) -> Union[Profile, bool]:
        """Check if a profile, by name, exists."""
        return next(
            filter(lambda prf: prf.profile_name == profile_name, self.profiles), False
        )

    def _alias_exists(self, *, alias_name: str) -> Union[ProfileAlias, bool]:
        """Check if an alias, by name, exists."""
        return next(
            filter(lambda ally: ally.alias == alias_name, self.alias_list), False
        )

    def _address_exists(self, *, address: str) -> Union[str, bool]:
        """Check if address is valid."""
        return next(filter(lambda addy: addy == address, self.address_list), False)

    def _key_exists(self, *, key_string: str) -> Union[ProfileKey, bool]:
        """Check if key string exists."""
        return next(
            filter(lambda pkey: pkey.private_key_base64 == key_string, self.key_list),
            False,
        )

    @property
    def active_address(self) -> str:
        """Return the active address."""
        return self.using_address

    @active_address.setter
    def active_address(self, change_to: str) -> str:
        """Set the using address to change_to."""
        _ = self.address_list.index(change_to)
        self.using_address = change_to
        return change_to

    @property
    def active_alias(self) -> str:
        """Return the alias associated to the using (active) address."""
        adex = self.address_list.index(self.using_address)
        return self.alias_list[adex].alias

    @active_alias.setter
    def active_alias(self, change_to: str) -> str:
        """Change the alias that is active."""
        # Find the index of the change_to alias
        _res = self._alias_exists(alias_name=change_to)
        if _res:
            aliindx = self.alias_list.index(_res)
            self.using_address = self.address_list[aliindx]
            return _res.alias
        raise ValueError(f"Alias {change_to} not found in group")

    def address_for_alias(self, *, alias: str) -> str:
        """Get address associated with alias."""
        _res = self._alias_exists(alias_name=alias)
        if _res:
            aliindx = self.alias_list.index(_res)
            return self.address_list[aliindx]
        raise ValueError(f"Alias {alias} not found in group")

    def alias_for_address(self, *, address: str) -> ProfileAlias:
        """Get alias associated with address."""
        _res = self._address_exists(address=address)
        if _res:
            adindex = self.address_list.index(_res)
            return self.alias_list[adindex]
        raise ValueError(f"Address {address} not found in group")

    def alias_name_for_address(self, *, address: str) -> str:
        """Get alias associated with address."""
        _res = self._address_exists(address=address)
        if _res:
            adindex = self.address_list.index(_res)
            return self.alias_list[adindex].alias
        raise ValueError(f"Address {address} not found in group")

    def replace_alias_name(self, *, from_alias: str, to_alias: str) -> str:
        """Replace alias name and return associated address."""
        _res = self._alias_exists(alias_name=from_alias)
        if _res:
            _rese = self._alias_exists(alias_name=to_alias)
            if not _rese:
                aliindx = self.alias_list.index(_res)
                _res.alias = to_alias
                return self.address_list[aliindx]
            raise ValueError(f"Alias {to_alias} already exists")
        raise ValueError(f"Alias {from_alias} not found in group")

    @property
    def active_profile(self) -> Profile:
        """Gets the active profile."""
        _res = self._profile_exists(profile_name=self.using_profile)
        if _res:
            return _res
        raise ValueError(f"Profile {self.using_profile} not found in group")

    @active_profile.setter
    def active_profile(self, change_to: str) -> Profile:
        """Set the using Profile to change_to."""
        # Validate it exists
        _res = self._profile_exists(profile_name=change_to)
        if _res:
            self.using_profile = change_to
            return _res
        raise ValueError(f"{change_to} profile does not exist")

    def address_keypair(self, *, address: str) -> crypto.SuiKeyPair:
        """Fetch an addresses KeyPair."""
        _res = self._address_exists(address=address)
        if _res:
            return crypto.keypair_from_keystring(
                self.key_list[self.address_list.index(_res)].private_key_base64
            )

    @staticmethod
    def _alias_check_or_gen(
        *,
        aliases: Optional[list[str]] = None,
        word_counts: Optional[int] = 12,
        alias: Optional[str] = None,
        current_iter: Optional[int] = 0,
    ) -> str:
        """_alias_check_or_gen If alias is provided, checks if unique otherwise creates one or more.

        :param aliases: List of existing aliases, defaults to None
        :type aliases: list[str], optional
        :param word_counts: Words count used for mnemonic phrase, defaults to 12
        :type word_counts: Optional[int], optional
        :param alias: An inbound alias, defaults to None
        :type alias: Optional[str], optional
        :param current_iter: Internal recursion count, defaults to 0
        :type current_iter: Optional[int], optional
        :return: An aliases
        :rtype: str
        """
        if not alias:
            parts = list(
                utils.partition(
                    crypto.gen_mnemonic_phrase(word_counts).split(" "),
                    int(word_counts / 2),
                )
            )
            alias_names = [k + "-" + v for k, v in zip(*parts)]

            # alias_names = self._alias_gen_batch(word_counts=word_counts)
            # Find a unique part if just_one
            if not aliases:
                alias = alias_names[0]
            else:
                for alias_name in alias_names:
                    if alias_name not in aliases:
                        # Found one
                        alias = alias_name
                        break
            # If all match (unlikely), try unless threshold
            if not alias:
                if current_iter > 2:
                    raise ValueError("Unable to find unique alias")
                else:
                    alias = ProfileGroup._alias_check_or_gen(
                        aliases=aliases,
                        word_counts=word_counts,
                        current_iter=current_iter + 1,
                    )
        else:
            if alias in aliases:
                raise ValueError(f"Alias {alias} already exists.")
            if not (SUI_MIN_ALIAS_LEN <= len(alias) <= SUI_MAX_ALIAS_LEN):
                raise ValueError(
                    f"Invalid alias string length, must be betwee {SUI_MIN_ALIAS_LEN} and {SUI_MAX_ALIAS_LEN} characters."
                )
        return alias

    @staticmethod
    def new_keypair_parts(
        *,
        of_keytype: Optional[SignatureScheme] = SignatureScheme.ED25519,
        word_counts: Optional[int] = 12,
        derivation_path: Optional[str] = None,
        alias: Optional[str] = None,
        alias_list: list[ProfileAlias],
    ) -> tuple[str, str, ProfileKey, ProfileAlias]:
        """."""
        mnem, keypair = crypto.create_new_keypair(
            scheme=of_keytype,
            word_counts=word_counts,
            derv_path=derivation_path,
        )
        _new_keystr = keypair.serialize()
        _new_prf_key = ProfileKey(_new_keystr)
        # Generate artifacts
        _pkey_bytes = keypair.to_bytes()
        _digest = _pkey_bytes[0:33] if _pkey_bytes[0] == 0 else _pkey_bytes[0:34]
        # ProfileAlias Entry
        if not alias:
            alias = ProfileGroup._alias_check_or_gen(
                aliases=alias_list, alias=alias, word_counts=word_counts
            )

        _new_alias = ProfileAlias(
            alias,
            base64.b64encode(keypair.public_key.scheme_and_key()).decode(),
        )
        _new_addy = format(f"0x{hashlib.blake2b(_digest, digest_size=32).hexdigest()}")
        return mnem, _new_addy, _new_prf_key, _new_alias

    def add_keypair_and_parts(
        self,
        *,
        new_address: str,
        new_alias: ProfileAlias,
        new_key: ProfileKey,
        make_active: Optional[bool] = False,
    ) -> str:
        """Add a new keypair with associated address and alias."""

        if not self._key_exists(key_string=new_key.private_key_base64):
            if self._alias_exists(alias_name=new_alias.alias):
                raise ValueError(
                    f"Alias {new_alias.alias} already exist attempting new key and address."
                )
            # Populate group
            self.address_list.append(new_address)
            self.key_list.append(new_key)
            self.alias_list.append(new_alias)

            if make_active:
                self.using_address = new_address

        raise ValueError(
            f"Private keystring {new_key.private_key_base64} already exists attempting new key and address.."
        )

    def add_profile(self, *, new_prf: Profile, make_active: bool = False):
        """Add profile to list after validating name"""
        _res = self._profile_exists(profile_name=new_prf.profile_name)
        if _res:
            raise ValueError(f"Profile {new_prf.profile_name} already exists.")
        self.profiles.append(new_prf)
        if make_active:
            self.active_profile = new_prf.profile_name
