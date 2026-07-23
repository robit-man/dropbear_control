# ESP32 security platform intake

This intake separates three claims that must not be conflated:

1. a security feature exists somewhere in the installed SDK;
2. the active build profile enables and binds that feature; and
3. an exact physical controller was independently observed, provisioned and
   selected.

Only the third state may select a production security profile. Selection still
does not grant support, physical I/O or motion authority.

## Tracked observation

`securityprofile-cb147fcc2ea981c64c9b` binds the current `esp32` PlatformIO
environment and the exact locally installed inputs:

| Component | Observed version | SHA-256 |
|---|---|---|
| PlatformIO Espressif32 platform | 7.0.1 | `cf91a737e86cc22d670e56f19139a2db56f461ba5b952670c3f38bfe84dce7c3` |
| Arduino-ESP32 framework package | `3.20017.241212+sha.dcc1105b` (Arduino-ESP32 2.0.17 package line) | `f35415c75f6f43755df92bbbf7ef10c9e65c2edb2569d512636a0477be64d5bf` |
| ESP-IDF version header | 4.4.7 | `56be0b78266695b3b2a5fd8af5e8661e26e270f7ea35cf0961b9444712c09aaa` |
| ESP32 SDK configuration | active package profile | `a4fe490abd8cd6447874edd79bde1e78d9630af7845bd53f70440a56b3504907` |
| Arduino default partition table | active package profile | `3057e2f0b65ffb81f250ba592702c1512cea0ade043ed9baf869ec30987c1290` |
| Project `platformio.ini` | `esp32` / `esp32dev` / Arduino | `1ddc2e9da69f557265db2a0b72bf3873bd245c09e1f03fa0a442335b1b5c1b48` |

No absolute home-directory path is persisted. The validator resolves the
profile's PlatformIO-home-relative paths and rejects missing or changed bytes.

The active package profile has mbedTLS, the certificate bundle, TLS 1.2,
application rollback and two OTA application slots. It also compiles TLS 1.0
and TLS 1.1. Secure Boot, flash encryption, bootloader anti-rollback, NVS
encryption and secure-element use are disabled. The default partition table
has no dedicated persistent security-state partition. Application rollback
does not establish artifact authenticity and is not bootloader anti-rollback.

Therefore the generated status remains:

- one offline-observed candidate;
- zero independently reviewed or selected target profiles;
- zero trust anchors and key assignments;
- zero authenticated-transport, signed-artifact, persistent-replay,
  durable-audit or OTA-installer adapter bindings; and
- no support, physical I/O or motion authority.

## Promotion contract

A reviewed target profile can be selected only when all of these are present:

- exact installed asset, chip model/revision and redacted eFuse-summary digest;
- evidence that the chip revision supports the selected secure-boot design;
- release-mode flash encryption, Secure Boot, bootloader anti-rollback,
  encrypted NVS and an encrypted persistent security-state partition;
- TLS 1.2 with TLS 1.0/1.1 disabled;
- separately bound authenticated transport, signed-artifact verifier,
  reboot-persistent replay store, durable audit sink and OTA installer;
- seven non-reused key purposes with terminating roots, custody, rotation,
  revocation and provisioning evidence; and
- an independent, non-automated UTC review with unresolved blockers removed.

The firmware-release root for the current classic-ESP32 candidate must
terminate at reviewed Secure Boot V2 eFuse state and use the platform-supported
RSA-PSS-3072/SHA-256 profile. Other artifact and identity algorithms remain
open until their actual verifier and target are reviewed. A local JSON hash or
a key stored only in the same mutable data it verifies is not a trust anchor.

## Commands and evidence boundary

```sh
python3 tools/manage_security_platform_intake.py --check
tests/security_platform_intake/run_tests.sh
```

The tests include a synthetic positive selection to prove the lifecycle is not
denial-only. Synthetic evidence never changes the tracked status and never
represents physical provisioning.

The platform behavior references are the official ESP-IDF 4.4.7 documentation
for [ESP-TLS](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32/api-reference/protocols/esp_tls.html),
[Secure Boot V2](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32/security/secure-boot-v2.html),
and [flash encryption](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32/security/flash-encryption.html).
The exact installed bytes, not the documentation URL alone, are the active
source-bound observation.
