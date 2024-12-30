import sys
sys.path.append('./')


from substrateinterface import SubstrateInterface


URL = 'wss://docker-test.peaq.network'
URL = 'wss://mpfn1.peaq.network'
INFLAITON_PERCENTAGE = 0.035
COLLATR_DELEGATOR_PERCENTAGE = 0.40
TOTAL_ISSUANCE_NUMBER = 4.2 * 10 ** 9 * 10 ** 18


if __name__ == '__main__':
    substrate = SubstrateInterface(URL)
    now_collators = substrate.query(
        module='Session',
        storage_function='Validators',
    )
    now_collators = now_collators.value
    candidate_pool = substrate.query_map(
        module='ParachainStaking',
        storage_function='CandidatePool',
        start_key=None,
        page_size=1000,
    )
    candidate_pool = {k.value: v.value for k, v in candidate_pool.records}
    in_candidate_pool = {collator: candidate_pool[collator] for collator in now_collators}
    print(in_candidate_pool)

    total_staking_number = sum([value['total'] for value in in_candidate_pool.values()])
    print(total_staking_number)

    for k, v in in_candidate_pool.items():
        print(f'collator: {k}')
        print(f'    collator total: {v["total"]}')
        # commission_rate = v['commission'] / 10000000
        commission_rate = 0.1
        print(f'    commission rate: {commission_rate}')
        for delegator in v['delegators']:
            print(f'    delegator: {delegator["owner"]}')
            print(f'        delegator stake: {delegator["amount"]}')
            print(f'        delegator apr: {(INFLAITON_PERCENTAGE * COLLATR_DELEGATOR_PERCENTAGE * TOTAL_ISSUANCE_NUMBER * (1 - commission_rate) * delegator["amount"] / total_staking_number / delegator["amount"] * 100)}')
            print(f'        sum: {total_staking_number}')
        print(f'     collator apr: {(INFLAITON_PERCENTAGE * COLLATR_DELEGATOR_PERCENTAGE * TOTAL_ISSUANCE_NUMBER * (v["stake"] + commission_rate * sum([delegator["amount"] for delegator in v["delegators"]])) / total_staking_number / v["stake"] * 100)}')
