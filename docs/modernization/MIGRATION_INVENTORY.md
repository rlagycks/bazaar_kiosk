# 1A migration 원본 인벤토리

기준: develop `3604ccad7add5c760c3b1cecfaa7032706ddc01c` (PR38 머지). migration 파일은
`ff013b4b4934087dfa3f3e3ad368af9387554381`(PR36 머지)과도 바이트 동일하므로 두 기준의 결과는 같다.
이 표는 저장소 파일의 SHA256이며 운영 DB의 적용 완료 목록이 아니다.
검증에서 파일을 fake 적용하지 않는다. **0020은 D-P07 승인으로2026-09-08에 수정했고
나머지19개는 기준 커밋과 바이트 동일하다.** 수정 전0020 해시는
`b2ccbd94aea0c5bab15af7dc365e413bbebfb037e36edfef11d37b2056531ea6`이며 그 사본은
[orders/tests/original_0020.py](../../orders/tests/original_0020.py)에 보존한다.

| 파일 | SHA256 |
| --- | --- |
| [0001_initial.py](../../orders/migrations/0001_initial.py) | `6f49c408a48c3f0b7084815c5439c45302160d9161b503aaa7a78bcb1a8417a1` |
| [0002_pickupcounter_alter_table_options_and_more.py](../../orders/migrations/0002_pickupcounter_alter_table_options_and_more.py) | `090ddbd3f781e4c94c54177221ae65a737a492091afbb9fcc73653b99f461c9b` |
| [0003_add_is_pickup_call_and_clean.py](../../orders/migrations/0003_add_is_pickup_call_and_clean.py) | `849420f24de142dedf0ca5e23afef200fc5ddc112018e4063cdc69d9f713d168` |
| [0004_alter_table_options_and_more.py](../../orders/migrations/0004_alter_table_options_and_more.py) | `ec29521a67c0f8bf157eed2110baa586229a8f2e4a538c3db58db5699daa8256` |
| [0005_menuitem_channel_menuitem_created_at_and_more.py](../../orders/migrations/0005_menuitem_channel_menuitem_created_at_and_more.py) | `8b675fab973a1fbfc1a66e92498a216d98d59e580a516b1ecc4d07ec945d41e4` |
| [0006_menuitem_visibility_flags.py](../../orders/migrations/0006_menuitem_visibility_flags.py) | `0a74c5f5dafb4b40e2cb2a447698c623c492b300756b097af132338d8f49ee7e` |
| [0007_alter_menuitem_options_alter_table_options_and_more.py](../../orders/migrations/0007_alter_menuitem_options_alter_table_options_and_more.py) | `020f0691f72d94f81e69a8cce7009ef82c3bc0b681ba25499b24ebf0b8b02200` |
| [0008_delete_pickupcounter_alter_menucategory_options_and_more.py](../../orders/migrations/0008_delete_pickupcounter_alter_menucategory_options_and_more.py) | `0e29b3eecb80c336d8b7955879df39ad20c4dadc9ebb150559d74861c12d2da5` |
| [0009_pickupcounter_and_more.py](../../orders/migrations/0009_pickupcounter_and_more.py) | `b4148f4b94321cfddbb9048744491d2c80b27a4dbd269b103894681b26f52ab7` |
| [0010_floorordercounter_delete_pickupcounter_and_more.py](../../orders/migrations/0010_floorordercounter_delete_pickupcounter_and_more.py) | `7b2c27a2e6e457c6ecd4e94140ef891491c2c32cca66ff7d3011921f741139d1` |
| [0011_alter_floorordercounter_options_and_more.py](../../orders/migrations/0011_alter_floorordercounter_options_and_more.py) | `9b63a1d0ea3199e81293402e834f318d6b2f5621b66b1c91a9ebe15c9bdb795c` |
| [0012_alter_order_floor.py](../../orders/migrations/0012_alter_order_floor.py) | `fe81c5151a496ff1d4e14b92ac075f0b8a7b9fb689b2cb738fc9588b67e5e412` |
| [0013_orderitem_prepared_qty_and_cancel_status.py](../../orders/migrations/0013_orderitem_prepared_qty_and_cancel_status.py) | `0e4d421d5be6c3538ae54b23dab63810b79d29dc74e6fd06c310e8f237b905fc` |
| [0014_orderitem_service_mode.py](../../orders/migrations/0014_orderitem_service_mode.py) | `10352de301a9a8ae528427737111e74fc1ff36ec3bfa703fb201567a6ab295db` |
| [0015_remove_menu_categories.py](../../orders/migrations/0015_remove_menu_categories.py) | `a733d94b2101fda2b6559f723783e91b63670f238d643d617bc6d29358dccabf` |
| [0016_menuitem_index_if_missing.py](../../orders/migrations/0016_menuitem_index_if_missing.py) | `ae5308ecdace94c8ff3e97049a202de96665ee79a6002edd0fc1b80709f9bd92` |
| [0017_order_payment_split.py](../../orders/migrations/0017_order_payment_split.py) | `8edefc7c24c9d566db3ac9d497bec6d4dd78fb826758bc5abee23a3d9edc3516` |
| [0018_alter_order_floor_alter_order_order_type_and_more.py](../../orders/migrations/0018_alter_order_floor_alter_order_order_type_and_more.py) | `44221521317d84ce5b555af70d39f49c82739b50c2a1f8b32d7a8a46521d9041` |
| [0019_remove_order_orders_table_rule_and_more.py](../../orders/migrations/0019_remove_order_orders_table_rule_and_more.py) | `126eda2c35ea7288307300cf9259c237b089f615bb49bfa447da21d87695c506` |
| [0020_create_floor_sequences.py](../../orders/migrations/0020_create_floor_sequences.py) | `dbde0d9cc2843a33f69c47ba02491d6bf4c457e0297cfb7fa456ca0ba1c79d33` (D-P07 수정본) |

## 경로별 이력 확인

- 빈 DB는0001~0020이 모두 적용되고 sequence가(1,false)로 남아야 한다.
  수정 전 원본0020을 같은 빈 DB에 적용하면 여전히22003으로 실패하고0019 head에 남는다.
-0018 합성 과거 행의0019 실패 뒤에는0019 적용 행이 없어야 하며 제약 정의도 이전 상태여야 한다.
-0019 양수 번호40 사례의0020은1회만 기록되고 다시 적용할 계획이 없어야 한다.
- 원본0020으로 이미 적용된 DB에 수정본을 두어도 계획이 비어 있고 sequence 값이 유지돼야 한다.
- 적용 이력이 없는데 동명 sequence가 있으면42P07로 중단하고 그 값을 바꾸지 않아야 한다.
-0019 포장행의 역이행 실패 뒤에는0019 적용 이력이 그대로 남아야 한다.
- RunPython0014는 default manager를 사용한다. fixture가 default를 임시 DB로 바꾸는 이유이며,
  여러 DB alias에 안전한 앱이라는 주장을 하지 않는다.

## 운영 자료가 있어야 확정할 사항

1. 실제 운영 migration 적용 목록과 배포 산출물 해시가 이 저장소와 일치하는지.
2.0018/0019/0020 중 실제 head, 포장 table NULL/있음과 F1/BOOTH·번호 NULL/양수 행 수.
3. 원본/백업 DB 버전·확장·역할·sequence와 복원 가능한 별도 대상.
4. 과거 행의 보존·조회·테이블 의미와 번호 정책(D-008/017). 사용자 데이터 삭제/임의 재배정 금지.
5. 운영 DB의 실제 sequence 존재·값·소유권. 0020 수정본은 신규/미적용 경로만 고치며
   이미 적용된 DB의 sequence 누락·드리프트를 자동 복구하지 않는다.

운영에 접속하거나 원본 데이터를 추출하지 않았다. 해당 증거가 없는 상태에서 과거 migration
복구 전략을 승인된 것으로 기록하지 않는다. 재현 명령은 [PG 테스트 안내](POSTGRES_TESTING.md)를 따른다.
