from pathlib import Path

from tools.import_go_csv_devices import convert_csv_devices


def test_convert_csv_devices(tmp_path: Path) -> None:
    zones = tmp_path / "zones.csv"
    zones.write_text(
        "zone_id,zone_code,name,alias,disabled,deleted,created_at,updated_at,version\n"
        '9,2,Quarto Bebe,"",false,false,x,x,1\n'
    )
    devices = tmp_path / "devices.csv"
    devices.write_text(
        "device_id,device_code,section_code,name,type,alias,disabled,deleted,"
        "created_at,updated_at,version,zone_id\n"
        "20,0,0,Teto,light,baby_room_ceiling_light,false,false,x,x,1,9\n"
        "23,0,1,Estore,blind,baby_room_blind,false,false,x,x,1,9\n"
    )

    converted = convert_csv_devices(zones, devices)

    assert converted[0]["key"] == "baby_room_ceiling_light"
    assert converted[0]["name"] == "Teto"
    assert converted[0]["kind"] == "light"
    assert converted[0]["zone_code"] == 2
    assert converted[0]["section_code"] == 0
    assert converted[0]["device_code"] == 0
    assert converted[1]["key"] == "baby_room_blind"
    assert converted[1]["kind"] == "cover"
