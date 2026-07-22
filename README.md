# Israel Electric Company (IEC) Home Assistant integration

This repository provides a Home Assistant custom integration that authenticates with the Israel Electric Company customer API using an Israeli ID number and the IEC one-time code (SMS is preferred when available).

It creates Energy-dashboard-compatible cumulative sensors for:

- Total imported energy (kWh)
- Total exported energy (kWh)
- Import and export in IEC's latest reporting period

Meter serial/code, reporting period, IEC status, interval import/export readings, and every meter-register reading returned by IEC are retained as sensor attributes.

## Install

Copy `custom_components/iec` into your Home Assistant `config/custom_components` directory, restart Home Assistant, then add **Israel Electric Company (IEC)** from **Settings → Devices & services**. Enter the ID number that is registered with IEC and complete the OTP challenge.

The integration polls hourly. IEC's customer API supplies billing/smart-meter data, not real-time power, so this integration intentionally exposes energy totals rather than a power sensor.
