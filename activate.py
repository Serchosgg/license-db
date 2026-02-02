#!/usr/bin/env python3
"""
activate.py — Lógica de activación de licencias.

Este script se ejecuta DENTRO de GitHub Actions (en la nube de GitHub).
Nunca se ejecuta en la máquina del cliente.

Recibe los datos por variables de entorno (las pasa el workflow .yml).
Lee licenses.json, valida, actualiza, y escribe el resultado en results/{requestId}.json
"""

import json
import hashlib
import os
from datetime import datetime, timezone


# ============================================================
# LEER VARIABLES DE ENTORNO (las pasan desde el workflow)
# ============================================================
email       = os.environ.get("INPUT_EMAIL", "").strip().lower()
master_key  = os.environ.get("INPUT_MASTERKEY", "").strip().upper().replace("-", "")
machine_id  = os.environ.get("INPUT_MACHINEID", "").strip()
machine_name= os.environ.get("INPUT_MACHINENAME", "").strip()
request_id  = os.environ.get("INPUT_REQUESTID", "").strip()
encryption_key = os.environ.get("ENCRYPTION_KEY", "")
max_activations = int(os.environ.get("MAX_ACTIVATIONS", "1"))


# ============================================================
# FUNCIÓN: Generar master key esperada (mismo algoritmo que C#)
# Hash deterministico: SHA256(email|lifetime|ENCRYPTION_KEY)
# Toma los primeros 16 chars del hash en uppercase
# ============================================================
def generate_master_key(email_input: str) -> str:
    data = f"{email_input}|lifetime|{encryption_key}"
    hash_hex = hashlib.sha256(data.encode("utf-8")).hexdigest()
    key = hash_hex[:16].upper()
    return key  # sin guiones, solo los 16 chars


# ============================================================
# FUNCIÓN: Escribir resultado para que el cliente lo lea
# ============================================================
def write_result(success: bool, message: str, token: str = ""):
    os.makedirs("results", exist_ok=True)
    result = {
        "requestId": request_id,
        "success": success,
        "message": message,
        "activationToken": token,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    with open(f"results/{request_id}.json", "w") as f:
        json.dump(result, f, indent=2)
    print(f"[RESULT] success={success} | message={message}")


# ============================================================
# VALIDACIONES PREVIAS
# ============================================================
if not email or not master_key or not machine_id or not request_id:
    write_result(False, "Missing required fields.")
    exit(0)

if not encryption_key:
    write_result(False, "Server misconfigured. Contact support.")
    exit(0)


# ============================================================
# PASO 1: Validar master key
# ============================================================
expected_key = generate_master_key(email)
if master_key != expected_key:
    write_result(False, "Invalid license key or email. Please verify and try again.")
    exit(0)

print(f"[OK] Master key validated for {email}")


# ============================================================
# PASO 2: Leer licenses.json
# ============================================================
LICENSES_FILE = "licenses.json"

if os.path.exists(LICENSES_FILE):
    with open(LICENSES_FILE, "r") as f:
        db = json.load(f)
else:
    # Primera vez: crear estructura vacía
    db = {
        "version": "1.0",
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "licenses": []
    }

print(f"[OK] Loaded licenses.json — {len(db.get('licenses', []))} licenses found")


# ============================================================
# PASO 3: Buscar o crear entrada de licencia para este email
# ============================================================
license_entry = None
for lic in db["licenses"]:
    if lic["email"] == email:
        license_entry = lic
        break

if license_entry is None:
    # Primera activación para este email → crear entrada
    license_entry = {
        "email": email,
        "masterKey": master_key,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "isActive": True,
        "activations": []
    }
    db["licenses"].append(license_entry)
    print(f"[OK] Created new license entry for {email}")


# ============================================================
# PASO 4: Verificar si ya está activada en ESTA máquina
# ============================================================
already_active_here = False
for act in license_entry["activations"]:
    if act["machineId"] == machine_id:
        already_active_here = True
        break

if already_active_here:
    # Ya activada en esta PC → éxito sin necesidad de escribir nada nuevo
    token = hashlib.sha256(f"{email}|{machine_id}|activated|{encryption_key}".encode()).hexdigest()
    write_result(True, "License is active on this computer.", token)
    exit(0)


# ============================================================
# PASO 5: Verificar límite de activaciones
# ============================================================
active_count = len(license_entry["activations"])
if active_count >= max_activations:
    occupied = license_entry["activations"][0].get("machineName", "another computer")
    write_result(
        False,
        f'This license is already activated on "{occupied}". '
        f'Maximum allowed: {max_activations} computer(s). '
        f'Contact support to transfer your license.'
    )
    exit(0)


# ============================================================
# PASO 6: Todo libre → agregar activación
# ============================================================
new_activation = {
    "machineId": machine_id,
    "machineName": machine_name if machine_name else "Unknown",
    "activatedAt": datetime.now(timezone.utc).isoformat()
}
license_entry["activations"].append(new_activation)
db["lastUpdated"] = datetime.now(timezone.utc).isoformat()

print(f"[OK] Activation added for {email} on {machine_name}")


# ============================================================
# PASO 7: Guardar licenses.json actualizado
# ============================================================
with open(LICENSES_FILE, "w") as f:
    json.dump(db, f, indent=2)

print(f"[OK] licenses.json updated")


# ============================================================
# PASO 8: Escribir resultado exitoso
# ============================================================
token = hashlib.sha256(f"{email}|{machine_id}|activated|{encryption_key}".encode()).hexdigest()
write_result(True, "License activated successfully!", token)
