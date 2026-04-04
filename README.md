# 💾 WOW-TG-REG 

`WOW-TG-REG` is a lightweight, asynchronous Telegram bot written in Python (`aiogram 3.x`), designed for direct account management on classic World of Warcraft emulators (MaNGOS / CMangos / TrinityCore). 

Forget the clunky web wrappers of the 2000s. Direct MySQL access. Strict SRP6 generation. Maximum performance.

## 💽 SYSTEM FEATURES

* **[ CREATE ]** Registration of a new game account with the generation of SRP6 hashes `v` and `s` (generation is performed strictly according to emulator standards).
* **[ LINK ]** Hard binding of the account to the user's Telegram ID (1 TG = 1 Account), eliminating bot spam and multi-accounting.
* **[ UPDATE ]** On-the-fly password changing with instant overwriting of hashes in the `account` table.
* **[ DELETE ]** Complete erasure of account data from the database.

## ⚙️ INSTALLATION AND INITIALIZATION

**Step 1. Database Preparation (CRITICAL)**
To make the system work, you need to embed an additional column in the authentication table. Open your server terminal and execute the following SQL command to modify the `account` table:

```bash
mysql -umangos -pmangos classicrealmd -e "ALTER TABLE account ADD COLUMN tgid BIGINT DEFAULT NULL;"
