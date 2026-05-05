from tools.import_go_sql_devices import convert_sql_devices


def test_convert_sql_devices() -> None:
    device_insert = (
        'INSERT INTO public.devices ("device_id","created_at","updated_at", '
        '"type", "name", "device_code", "section_code", "zone_id", "alias")'
    )
    sql = f"""
    INSERT INTO public.zones VALUES (1, 5,'Cozinha', '',false,false,'x', 'x',1);
    {device_insert}
    VALUES (11, 'x', 'x', 'light', 'Teto', 0, 0, 1, 'kitchen_ceiling');
    {device_insert}
    VALUES (12, 'x', 'x', 'blind', 'Estore', 1, 1, 1, '');
    """

    devices = convert_sql_devices(sql)

    assert devices[0]["key"] == "kitchen_ceiling"
    assert devices[0]["kind"] == "light"
    assert devices[0]["zone_code"] == 5
    assert devices[0]["section_code"] == 0
    assert devices[0]["device_code"] == 0
    assert devices[1]["kind"] == "cover"
    assert devices[1]["name"] == "Estore"
