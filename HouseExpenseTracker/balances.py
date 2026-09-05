from __future__ import annotations


def simplify_debts(balances: dict[str, int]) -> list[tuple[str, str, int]]:
    creditors: list[list] = []
    debtors: list[list] = []
    for sender, balance in balances.items():
        if balance > 0:
            creditors.append([sender, balance])
        elif balance < 0:
            debtors.append([sender, -balance])
    creditors.sort(key=lambda item: -item[1])
    debtors.sort(key=lambda item: -item[1])
    transfers: list[tuple[str, str, int]] = []
    creditor_index = 0
    debtor_index = 0
    while creditor_index < len(creditors) and debtor_index < len(debtors):
        pay_amount = min(creditors[creditor_index][1], debtors[debtor_index][1])
        if pay_amount > 0:
            transfers.append((debtors[debtor_index][0], creditors[creditor_index][0], pay_amount))
        creditors[creditor_index][1] -= pay_amount
        debtors[debtor_index][1] -= pay_amount
        if creditors[creditor_index][1] == 0:
            creditor_index += 1
        if debtors[debtor_index][1] == 0:
            debtor_index += 1
    return transfers
