import socket
import json
import sys
import traceback
import time

ELFIN_IP = "192.168.1.47"
ELFIN_PORT = 8899
TIMEOUT = 2.0

def get_crc(cmd_bytes):
    crc = 0
    for b in cmd_bytes:
        crc = (crc ^ (b << 8)) & 0xFFFF
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    crc_h, crc_l = crc >> 8, crc & 0xFF
    if crc_h in (0x28, 0x0D, 0x0A): crc_h += 1
    if crc_l in (0x28, 0x0D, 0x0A): crc_l += 1
    return bytes([crc_h, crc_l])

def fetch_data(cmd_str):
    try:
        cmd_bytes = cmd_str.encode('ascii')
        payload = cmd_bytes + get_crc(cmd_bytes) + b'\r'
        
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(TIMEOUT)
        s.connect((ELFIN_IP, ELFIN_PORT))
        s.sendall(payload)
        data = s.recv(1024)
        s.close()
        
        clean_text = data.decode('ascii', errors='ignore').strip().lstrip('(').split('\x1b')[0].split('\r')[0]
        if clean_text == "NAK":
            return None
        return clean_text.split(' ')
    except:
        return None

try:
    # --- Блок запросов ---
    qpigs = fetch_data("QPIGS")
    time.sleep(0.3)
    
    qpiri = fetch_data("QPIRI")
    time.sleep(0.3)
    
    qpiws = fetch_data("QPIWS")
    time.sleep(0.3)
    
    qmod = fetch_data("QMOD")
    time.sleep(0.3)
    
    qflag = fetch_data("QFLAG")
    time.sleep(0.3)
    
    qid = fetch_data("QID")
    time.sleep(0.3)
    
    qvfw = fetch_data("QVFW")
    time.sleep(0.3)
    
    discovery = {}
    for cmd in ["QT", "QET", "QED", "QOPPT", "QCHPT"]:
        resp = fetch_data(cmd)
        if resp:
            discovery[cmd] = " ".join(resp)
        time.sleep(0.3)

    if not qpigs or len(qpigs) < 16:
        raise ValueError("Получен пустой или неполный ответ QPIGS")

    status_bits = qpigs[16] if len(qpigs) > 16 and len(qpigs[16]) >= 8 else "00000000"
    pv_watt = int(float(qpigs[12]) * float(qpigs[13]))

    result = {
        # --- Системная информация --- ⚙️
        "device_mode": qmod[0] if qmod else None,
        "device_serial": qid[0] if qid else None,
        "firmware_version": qvfw[0].replace('VERFW:', '') if qvfw else None,
        
        # --- Текущие метрики --- ⚡
        "grid_voltage": float(qpigs[0]),
        "grid_freq": float(qpigs[1]),
        "ac_output_voltage": float(qpigs[2]),
        "ac_output_freq": float(qpigs[3]),
        "ac_output_apparent_power": int(qpigs[4]),
        "load_watt": int(qpigs[5]),
        "load_percent": int(qpigs[6]),
        "bus_voltage": int(qpigs[7]),
        
        "battery_voltage": float(qpigs[8]),
        "battery_charge_current": int(qpigs[9]),
        "battery_capacity_percent": int(qpigs[10]),
        "heatsink_temp": int(qpigs[11]),
        "pv_current": float(qpigs[12]),
        "pv_voltage": float(qpigs[13]),
        "scc_voltage": float(qpigs[14]) if len(qpigs) > 14 else 0.0,
        "battery_discharge_current": int(qpigs[15]) if len(qpigs) > 15 else 0,
        "pv_watt": pv_watt,
        
        # --- Статусы оборудования --- 🔄
        "status_load_on": status_bits[3] == '1',
        "status_charging_on": status_bits[5] == '1',
        "status_solar_charging": status_bits[6] == '1',
        "status_grid_charging": status_bits[7] == '1',
        
        # --- Ошибки и флаги --- ⚠️
        "warnings_raw": qpiws[0] if qpiws else "no_data",
        "flags_raw": qflag[0] if qflag else None,
        
        # --- Номинальные параметры и лимиты (QPIRI) --- 📊
        "nominal_ac_output_voltage": float(qpiri[2]) if qpiri else None,
        "nominal_ac_output_freq": float(qpiri[3]) if qpiri else None,
        "nominal_ac_output_apparent_power": int(qpiri[5]) if qpiri else None,
        "nominal_ac_output_active_power": int(qpiri[6]) if qpiri else None,
        "nominal_battery_voltage": float(qpiri[7]) if qpiri else None,
        
        # --- Настройки пользователя (Меню инвертора) --- 🛠️
        "setting_batt_cutoff_voltage": float(qpiri[9]) if qpiri else None,
        "setting_batt_bulk_voltage": float(qpiri[10]) if qpiri else None,
        "setting_batt_float_voltage": float(qpiri[11]) if qpiri else None,
        "setting_battery_type": int(qpiri[12]) if qpiri else None,
        "setting_max_ac_charge_current": int(qpiri[13]) if qpiri else None,
        "setting_max_charge_current": int(qpiri[14]) if qpiri else None,
        "setting_input_voltage_range": int(qpiri[15]) if qpiri else None,
        "setting_output_priority": int(qpiri[16]) if qpiri else None,
        "setting_charger_priority": int(qpiri[17]) if qpiri else None,
        "setting_machine_type": int(qpiri[20]) if qpiri and len(qpiri) > 20 else None,
        "setting_topology": int(qpiri[21]) if qpiri and len(qpiri) > 21 else None,
        
        # --- Таймеры и Экспериментальные данные --- ⏱️
        "raw_discovery": discovery
    }
    
    print(json.dumps(result))

except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}))
    sys.exit(1)