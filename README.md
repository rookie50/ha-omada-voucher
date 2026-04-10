# Omada Hotspot Voucher – Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Custom Home Assistant integration for managing and displaying TP-Link Omada Hotspot voucher codes directly in your dashboard.

> **Created with the assistance of [Claude](https://claude.ai) (Anthropic)**

---

## Features

- 📊 **Voucher group sensors** – remaining unused count per group
- 🎫 **Voucher code sensors** – shows the next 2 unused codes per group, ready to share with guests
- 🔄 **Auto-refresh** – configurable polling interval (default 5 minutes)
- 🛎️ **Services** – create, delete, replenish voucher groups, reload codes on demand
- 🔁 **Automations** – trigger code refresh automatically when voucher counts change

---

## Requirements

- TP-Link Omada Controller **6.x**
- A controller admin account with access to the Hotspot Manager
- At least one voucher group configured in the Omada Hotspot Manager
- **Important:** Each voucher group must have a unique `duration` value (the integration uses this to distinguish groups when filtering codes)

---

## Installation

### Via HACS (recommended)

1. Add this repository as a custom repository in HACS:  
   `https://github.com/bremke/ha-omada-voucher`  
   Category: **Integration**
2. Install **Omada Hotspot Voucher**
3. Restart Home Assistant

### Manual

1. Copy the `custom_components/omada_voucher` folder into your HA `custom_components` directory
2. Restart Home Assistant

---

## Configuration

Go to **Settings → Devices & Services → Add Integration → Omada Hotspot Voucher**

| Field | Example | Required |
|-------|---------|----------|
| Controller URL | `https://omada.example.com` | ✅ |
| Username | `admin` | ✅ |
| Password | `yourpassword` | ✅ |
| Site Name | `Home` | ✅ |
| Scan Interval (seconds) | `300` | ✅ |

The integration automatically discovers the `omadacId` and `siteId` – no manual configuration needed.

---

## Entities

For each voucher group, the following entities are created:

| Entity | Example | Description |
|--------|---------|-------------|
| `sensor.voucher_{name}` | `sensor.voucher_tagesvoucher` | Remaining unused vouchers |
| `sensor.voucher_{name}_code_1` | `sensor.voucher_tagesvoucher_code_1` | Next available code (slot 1) |
| `sensor.voucher_{name}_code_2` | `sensor.voucher_tagesvoucher_code_2` | Next available code (slot 2) |

---

## Services

| Service | Description |
|---------|-------------|
| `omada_voucher.reload_codes` | Force refresh of voucher codes |
| `omada_voucher.create_vouchers` | Create a new voucher group |
| `omada_voucher.delete_group` | Delete a voucher group |
| `omada_voucher.replenish_group` | Add more vouchers to an existing group |

---

## Known Limitations

- The `/voucherGroups/{id}/vouchers` API endpoint requires a Hotspot Management session, which differs from the controller admin session. The integration works around this by fetching all vouchers and filtering client-side using the `duration` field of each voucher group. **This requires each group to have a unique duration.**
- Tested with Omada Controller 6.x behind a Zoraxy reverse proxy. Direct access may behave differently.
- The Hotspot Operator account (`HA-Voucher` type) is **not needed** – the standard controller admin account works for all required API calls.

---

## Example Dashboard Card

```yaml
type: custom:stack-in-card
cards:
  - type: markdown
    content: |
      ## 🎫 Tagesvoucher
      # {{ states('sensor.voucher_tagesvoucher_code_1') }}
      {{ states('sensor.voucher_tagesvoucher_code_2') }}
  - type: tile
    entity: sensor.voucher_tagesvoucher
    name: Verbleibend
```

---

## License

MIT License
