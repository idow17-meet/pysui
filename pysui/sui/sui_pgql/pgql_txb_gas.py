#    Copyright Frank V. Castellucci
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#        http://www.apache.org/licenses/LICENSE-2.0
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

# -*- coding: utf-8 -*-

import base64
from typing import Optional, Union
from pysui.sui.sui_pgql.pgql_txb_signing import SignerBlock
from pysui.sui.sui_pgql.pgql_clients import BaseSuiGQLClient
import pysui.sui.sui_pgql.pgql_types as pgql_type
import pysui.sui.sui_pgql.pgql_query as qn
from pysui.sui.sui_types import bcs


def _get_gas_objects(
    client: BaseSuiGQLClient, gas_ids: list[str]
) -> list[pgql_type.SuiCoinObjectGQL]:
    """Retreive specific Gas Objects."""
    result = client.execute_query(
        with_query_node=qn.GetMultipleGasObjects(coin_object_ids=gas_ids)
    )
    if result.is_ok():
        return result.result_data.data
    else:
        raise ValueError(f"Error retrieving coins by id {result.result_string}")


def _get_all_gas_objects(
    signing: SignerBlock, client: BaseSuiGQLClient
) -> list[pgql_type.SuiCoinObjectGQL]:
    """Retreive all Gas Objects."""
    payer = signing.payer_address
    coin_list: list[pgql_type.SuiCoinObjectGQL] = []
    result = client.execute_query(with_query_node=qn.GetCoins(owner=payer))
    while True:
        if result.is_ok():
            coin_list.extend(result.result_data.data)
            if result.result_data.next_cursor.hasNextPage:
                result = client.execute_query(
                    with_query_node=qn.GetCoins(
                        owner=payer, next_page=result.result_data.next_cursor
                    )
                )
            else:
                break
        else:
            break
    return coin_list


def _dry_run_for_budget(
    signing: SignerBlock,
    client: BaseSuiGQLClient,
    tx_bytes: str,
    active_gas_price: int,
) -> int:
    """Perform a dry run when no budget specified."""
    result = client.execute_query(
        with_query_node=qn.DryRunTransactionKind(
            tx_bytestr=tx_bytes,
            tx_meta={
                "sender": signing.sender_str,
                "gasPrice": active_gas_price,
                "gasSponsor": signing.sponsor_str,
            },
            skip_checks=False,
        )
    )
    if result.is_ok():
        if result.result_data.transaction_block.effects["status"] == "SUCCESS":
            c_cost: int = int(
                result.result_data.transaction_block.effects["gasEffects"][
                    "gasSummary"
                ]["computationCost"]
            )
            s_cost: int = int(
                result.result_data.transaction_block.effects["gasEffects"][
                    "gasSummary"
                ]["storageCost"]
            )
            return c_cost + s_cost
        else:
            raise ValueError(f"{result.result_data.errors}")
    else:
        raise ValueError(
            f"Error running DryRunTransactionBlock: {result.result_string}"
        )


def _coins_for_budget(
    coins: list[pgql_type.SuiCoinObjectGQL], budget: int
) -> list[bcs.ObjectReference]:
    """."""
    _coin_fit = [x for x in coins if int(x.balance) > budget]
    if _coin_fit:
        _coin_fit = [_coin_fit[0]]
    else:
        _accum: int = 0
        _accum_coin: list = []
        for _coin in coins:
            if _accum >= budget:
                break
            else:
                _accum_coin.append(_coin)
                _accum += int(_coin.balance)
        if _accum < budget:
            raise ValueError(
                f"Total gas available {_accum}, transaction requires {budget}"
            )
        _coin_fit = _accum_coin
    return [bcs.ObjectReference.from_gql_ref(x) for x in _coin_fit]


def get_gas_data(
    *,
    signing: SignerBlock,
    client: BaseSuiGQLClient,
    budget: Optional[int] = None,
    use_coins: Optional[list[Union[str, pgql_type.SuiCoinObjectGQL]]] = None,
    objects_in_use: set[str],
    active_gas_price: int,
    tx_kind: bcs.TransactionKind,
) -> bcs.GasData:
    """get_gas_data Builds the GasData BCS structure for the transaction data.

    :param signing: The GraphQL SigningBlock
    :type signing: SignerBlock
    :param client: The GraphQL Client
    :type client: BaseSuiGQLClient
    :param objects_in_use: Objects already identified as 'in-use' in the builder
    :type objects_in_use: set[str]
    :param active_gas_price: Current Gas Price
    :type active_gas_price: int
    :param tx_kind: The TransactionKind BCS
    :type tx_kind: bcs.TransactionKind
    :param budget: Option budget to set for transaction, defaults to None
    :type budget: Optional[int], optional
    :param use_coins: Gas coins to use for paying transactions, defaults to None
    :type use_coins: Optional[list[Union[str, pgql_type.SuiCoinObjectGQL]]], optional
    :raises ValueError: If use_coins are not either strings or SuiCoinObjectGQL objects
    :raises ValueError: If not gas coins provided and none found
    :return: _description_
    :rtype: bcs.GasData
    """
    # Get available coins
    _specified_coins = True if use_coins else False
    if use_coins:
        if all(isinstance(x, str) for x in use_coins):
            use_coins = _get_gas_objects(client, use_coins)
        elif not all(isinstance(x, pgql_type.SuiCoinObjectGQL) for x in use_coins):
            raise ValueError("use_gas_objects must use same type.")
    else:
        use_coins = _get_all_gas_objects(signing, client)
    if not budget:
        budget = _dry_run_for_budget(
            signing,
            client,
            base64.b64encode(tx_kind.serialize()).decode(),
            active_gas_price,
        )
    # Remove conflicts with objects in use
    use_coins = [x for x in use_coins if x.coin_object_id not in objects_in_use]
    # Make sure something left to pay for
    if use_coins:
        # Return constructs for createing bcs.GasData
        return bcs.GasData(
            _coins_for_budget(use_coins, budget),
            bcs.Address.from_str(signing.payer_address),
            active_gas_price,
            budget,
        )
    raise ValueError("No coin objects found to fund transaction.")
