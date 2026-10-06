#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <MFRC522.h>
#include <LiquidCrystal_I2C.h>
#include <ESP32Servo.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"

// =====================================================
// KONFIGURASI WIFI & SUPABASE CLOUD (SESUAI WEB DASHBOARD)
// =====================================================
// Silakan ganti SSID & Password sesuai hotspot/WiFi Anda:
const char* WIFI_SSID     = "Nagato";
const char* WIFI_PASSWORD = "HadesNagato060301*";

// Kredensial Supabase Cloud Backend (Sesuai file .env website)
const char* SUPABASE_URL     = "https://wxowndnwwzryzdkdkkqx.supabase.co";
const char* SUPABASE_KEY     = "sb_publishable_mbfQ6EQ6imUsTxXroPUUnQ_jGWDuFTc";
const char* DEVICE_ID        = "DEV-SISWA-B94AC1"; // ID Controller Smart Parking (Master Node atau ID baru yang didaftarkan)
const char* DEVICE_API_KEY   = "sk_dev_d0279437202a767a697b51424013c6fe";        // Tempelkan API Key di sini (misal: "sk_dev_xxxx") yang Anda dapatkan saat registrasi device baru

// =====================================================
// PIN CONFIGURATION - ESP32
// =====================================================

// Servo Motor (Palang Gerbang Parkir)
#define PIN_SERVO           4

// LCD 16x2 I2C
#define LCD_SDA_PIN         16
#define LCD_SCL_PIN         17
#define LCD_I2C_ADDR        0x27

// IR Obstacle Sensors (Deteksi 3 Slot Parkir Mobil)
#define PIN_IR_SLOT1        32  // Slot 1 (Sudah terpasang)
#define PIN_IR_SLOT2        33  // Slot 2 (Pin baru)
#define PIN_IR_SLOT3        35  // Slot 3 (Pin baru, input-only bebas strapping)
#define IR_SLOT_DETECTED    LOW // Sebagian besar modul IR aktif LOW saat mobil ada di slot

// Ultrasonic HC-SR04 (Deteksi Mobil di Depan Gerbang)
#define PIN_TRIG            25
#define PIN_ECHO            26

// Buzzer
#define PIN_BUZZER          27

// RFID RC522 (VSPI)
#define RFID_SS             21
#define RFID_RST            22
#define RFID_SCK            18
#define RFID_MISO           19
#define RFID_MOSI           23

// =====================================================
// KONFIGURASI SISTEM PARKIR & TIMING
// =====================================================

const int TOTAL_SLOTS = 3; // Total kapasitas slot parkir mobil
#define ECHO_TIMEOUT 30000 // Batas waktu pembacaan echo HC-SR04 (µs)
const unsigned long SENSOR_INTERVAL_MS = 300; // Interval pembacaan sensor (ms)

// Ambang batas jarak untuk mendeteksi mobil di depan gerbang (cm)
const float CAR_DETECTION_DISTANCE_CM = 20.0;

// Tolak akses masuk jika semua slot parkir sudah terisi penuh
const bool BLOCK_ENTRY_IF_FULL = true;

// Konfigurasi Palang Gerbang Servo
const int SERVO_CLOSED_ANGLE = 0;   // Sudut derajat saat palang tertutup
const int SERVO_OPEN_ANGLE   = 90;  // Sudut derajat saat palang terbuka
const unsigned long GATE_OPEN_DURATION_MS = 5000; // Palang terbuka selama 5 detik

// =====================================================
// STRUKTUR DATA & RTOS HANDLES
// =====================================================

// Struktur pesan untuk antrean Buzzer
struct BuzzerMessage {
  int frequency;
  int durationMs;
};

// Struktur pesan untuk antrean Sinkronisasi RFID ke Cloud
struct RFIDScanMessage {
  char uid[32];
};

// Queue untuk mengontrol buzzer secara asinkron
QueueHandle_t xBuzzerQueue;

// Queue untuk sinkronisasi hasil tap RFID ke server cloud
QueueHandle_t xRFIDSyncQueue;

// Mutex untuk mengamankan akses ke Serial Monitor
SemaphoreHandle_t xSerialMutex;

// Mutex untuk sinkronisasi data antar task
SemaphoreHandle_t xDataMutex;

// Semaphore sinyal pemicu buka gerbang
SemaphoreHandle_t xGateOpenSemaphore;

// Objek Perangkat
MFRC522 rfid(RFID_SS, RFID_RST);
LiquidCrystal_I2C lcd(LCD_I2C_ADDR, 16, 2);
Servo gateServo;

// Data bersama antar task (Thread-safe)
float sharedDistance = -1.0;
bool sharedCarDetected = false;
bool sharedSlot1Available = true;
bool sharedSlot2Available = true;
bool sharedSlot3Available = true;
int sharedAvailableCount = TOTAL_SLOTS; // Jumlah slot yang masih kosong
int sharedRawIR1 = 1;
int sharedRawIR2 = 1;
int sharedRawIR3 = 1;
String sharedUID = "";
bool sharedAccessGranted = false;
bool sharedAccessDeniedNoCar = false;
bool sharedAccessDeniedSlotFull = false;
bool sharedAccessDeniedPassback = false;
bool sharedTailgatingDetected = false;
bool sharedRegistrationMode = false;   // Mode Registrasi Aktif dari Cloud/Website
bool sharedRegCardCaptured = false;    // Kartu baru berhasil di-tap saat mode registrasi
unsigned long rfidDisplayUntil = 0;

// Status Kesiapan Sistem & Loading Animasi (ESP32 Ready State)
bool sharedSystemReady = false;
String sharedLoadingStatus = "Inisialisasi";
int sharedLoadingProgress = 0;
bool sharedWiFiConnected = false;

// =====================================================
// FUNGSI BANTU ULTRASONIC
// =====================================================

float readDistance() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);

  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);

  digitalWrite(PIN_TRIG, LOW);

  unsigned long duration = pulseIn(PIN_ECHO, HIGH, ECHO_TIMEOUT);

  if (duration == 0) {
    return -1.0; // Tidak ada pantulan objek / di luar jangkauan
  }

  return (duration * 0.0343) / 2.0;
}

// Mengirim instruksi bunyi buzzer ke Queue RTOS tanpa memblokir task
void triggerBeep(int frequency, int durationMs) {
  BuzzerMessage msg = {frequency, durationMs};
  xQueueSend(xBuzzerQueue, &msg, 0);
}

// =====================================================
// RTOS TASK 1: BUZZER (Asinkron via Queue di Core 1)
// =====================================================

void TaskBuzzer(void *pvParameters) {
  BuzzerMessage msg;

  for (;;) {
    if (xQueueReceive(xBuzzerQueue, &msg, portMAX_DELAY) == pdTRUE) {
      tone(PIN_BUZZER, msg.frequency);
      vTaskDelay(pdMS_TO_TICKS(msg.durationMs));
      noTone(PIN_BUZZER);
    }
  }
}

// =====================================================
// RTOS TASK 2: SERVO GATE (Kontrol Palang Parkir di Core 1)
// =====================================================

void TaskGate(void *pvParameters) {
  gateServo.attach(PIN_SERVO, 500, 2400);
  gateServo.write(SERVO_CLOSED_ANGLE); // Awal mula gerbang tertutup

  for (;;) {
    if (xSemaphoreTake(xGateOpenSemaphore, portMAX_DELAY) == pdTRUE) {
      // 0. Cegah palang terbuka jika sistem belum siap
      bool isReady = false;
      if (xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
        isReady = sharedSystemReady;
        xSemaphoreGive(xDataMutex);
      }
      if (!isReady) {
        gateServo.write(SERVO_CLOSED_ANGLE);
        if (xSemaphoreTake(xSerialMutex, portMAX_DELAY) == pdTRUE) {
          Serial.println("[GERBANG] DITOLAK: Sistem belum siap, palang tetap terkunci!");
          xSemaphoreGive(xSerialMutex);
        }
        continue;
      }

      // 1. Buka palang gerbang
      gateServo.write(SERVO_OPEN_ANGLE);

      if (xSemaphoreTake(xSerialMutex, portMAX_DELAY) == pdTRUE) {
        Serial.println("[GERBANG] Palang TERBUKA! Mobil silakan lewat.");
        xSemaphoreGive(xSerialMutex);
      }

      // 2. Tahan palang terbuka selama durasi yang ditentukan (5 detik)
      vTaskDelay(pdMS_TO_TICKS(GATE_OPEN_DURATION_MS));

      // 3. Tutup kembali palang gerbang
      gateServo.write(SERVO_CLOSED_ANGLE);

      if (xSemaphoreTake(xSerialMutex, portMAX_DELAY) == pdTRUE) {
        Serial.println("[GERBANG] Palang TERTUTUP kembali.");
        xSemaphoreGive(xSerialMutex);
      }

      // 4. Deteksi Tailgating (Mobil Membuntuti saat Palang Menutup)
      vTaskDelay(pdMS_TO_TICKS(400));
      float postGateDist = readDistance();
      if (postGateDist > 0 && postGateDist <= CAR_DETECTION_DISTANCE_CM) {
        if (xSemaphoreTake(xDataMutex, portMAX_DELAY) == pdTRUE) {
          sharedTailgatingDetected = true;
          xSemaphoreGive(xDataMutex);
        }
        if (xSemaphoreTake(xSerialMutex, portMAX_DELAY) == pdTRUE) {
          Serial.println();
          Serial.println("*************************************************");
          Serial.println(" [ALARM SECURITY] DETEKSI TAILGATING TERJADI!   ");
          Serial.println(" Kendaraan membuntuti tanpa otorisasi kartu!    ");
          Serial.println("*************************************************");
          Serial.println();
          xSemaphoreGive(xSerialMutex);
        }
        // Bunyikan sirene alarm (nada tinggi berulang)
        triggerBeep(3200, 150);
        vTaskDelay(pdMS_TO_TICKS(100));
        triggerBeep(3200, 150);
        vTaskDelay(pdMS_TO_TICKS(100));
        triggerBeep(3200, 300);
      }
    }
  }
}

// =====================================================
// RTOS TASK 3: SENSORS (Ultrasonic Gerbang & 3 IR Slot di Core 0)
// =====================================================

void TaskSensors(void *pvParameters) {
  bool sensorAnnounced = false;

  for (;;) {
    // 0. CEK KESIAPAN SISTEM SECARA MUTLAK:
    // Selama sistem BELUM siap (WiFi belum connect / cloud sync belum siap),
    // SENSOR TIDAK BOLEH MEMULAI APAPUN (Dilarang membaca jarak ultrasonik & dilarang membaca IR slot)!
    bool isReady = false;
    if (xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
      isReady = sharedSystemReady;
      xSemaphoreGive(xDataMutex);
    }

    if (!isReady) {
      sensorAnnounced = false;
      vTaskDelay(pdMS_TO_TICKS(250));
      continue; // SENSOR TETAP DORMANT / OFF (TIDAK MEMULAI APAPUN)
    }

    if (!sensorAnnounced) {
      sensorAnnounced = true;
      if (xSemaphoreTake(xSerialMutex, portMAX_DELAY) == pdTRUE) {
        Serial.println();
        Serial.println("========================================================");
        Serial.println(" [Sensor] SISTEM SIAP: Seluruh sensor mulai diaktifkan! ");
        Serial.println(" [Sensor] Memulai pembacaan HC-SR04 & IR 3 Slot Parkir  ");
        Serial.println("========================================================");
        Serial.println();
        xSemaphoreGive(xSerialMutex);
      }
    }

    // 1. Baca sensor ultrasonic (deteksi mobil di depan gerbang)
    float distance = readDistance();
    bool carAtGate = (distance > 0 && distance <= CAR_DETECTION_DISTANCE_CM);

    // 2. Baca 3 sensor IR slot parkir (LOW = Terisi / Mobil Ada, HIGH = Available / Kosong)
    int raw1 = digitalRead(PIN_IR_SLOT1);
    int raw2 = digitalRead(PIN_IR_SLOT2);
    int raw3 = digitalRead(PIN_IR_SLOT3);

    bool avail1 = (raw1 != IR_SLOT_DETECTED);
    bool avail2 = (raw2 != IR_SLOT_DETECTED);
    bool avail3 = (raw3 != IR_SLOT_DETECTED);

    int availCount = (avail1 ? 1 : 0) + (avail2 ? 1 : 0) + (avail3 ? 1 : 0);

    // Simpan data sensor ke variabel bersama secara thread-safe
    if (xSemaphoreTake(xDataMutex, portMAX_DELAY) == pdTRUE) {
      sharedDistance = distance;
      sharedCarDetected = carAtGate;
      sharedSlot1Available = avail1;
      sharedSlot2Available = avail2;
      sharedSlot3Available = avail3;
      sharedAvailableCount = availCount;
      sharedRawIR1 = raw1;
      sharedRawIR2 = raw2;
      sharedRawIR3 = raw3;
      xSemaphoreGive(xDataMutex);
    }

    // Log status ke Serial Monitor
    if (xSemaphoreTake(xSerialMutex, portMAX_DELAY) == pdTRUE) {
      Serial.print("[Sensor] Gerbang: ");
      if (carAtGate) {
        Serial.print("ADA MOBIL (");
      } else {
        Serial.print("Kosong    (");
      }
      if (distance < 0) Serial.print("--");
      else Serial.print(distance, 1);
      Serial.print(" cm) | Slot: [S1:");
      Serial.print(avail1 ? "O" : "X");
      Serial.print("|S2:");
      Serial.print(avail2 ? "O" : "X");
      Serial.print("|S3:");
      Serial.print(avail3 ? "O" : "X");
      Serial.print("] Sisa: ");
      Serial.print(availCount);
      Serial.print("/");
      Serial.print(TOTAL_SLOTS);
      Serial.print(" | RAW: ");
      Serial.print(raw1);
      Serial.print(",");
      Serial.print(raw2);
      Serial.print(",");
      Serial.println(raw3);
      xSemaphoreGive(xSerialMutex);
    }

    vTaskDelay(pdMS_TO_TICKS(SENSOR_INTERVAL_MS));
  }
}

// =====================================================
// RTOS TASK 4: RFID READER (Akses Gerbang di Core 1)
// =====================================================

void TaskRFID(void *pvParameters) {
  unsigned long lastRFIDReadTime = 0;
  String lastScannedUID = "";
  bool rfidAnnounced = false;

  for (;;) {
    // 0. Tunggu hingga proses booting & loading sistem selesai (WiFi & Cloud Siap)
    bool isReady = false;
    if (xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
      isReady = sharedSystemReady;
      xSemaphoreGive(xDataMutex);
    }
    if (!isReady) {
      rfidAnnounced = false;
      vTaskDelay(pdMS_TO_TICKS(200));
      continue; // JANGAN BACA KARTU SEBELUM SISTEM SIAP!
    }

    if (!rfidAnnounced) {
      rfidAnnounced = true;
      if (xSemaphoreTake(xSerialMutex, portMAX_DELAY) == pdTRUE) {
        Serial.println(" [RFID] Reader RC522 Aktif & Siap Memindai Kartu.");
        xSemaphoreGive(xSerialMutex);
      }
    }

    // 1. Cek kartu baru atau bangunkan kartu di area reader (WUPA)
    bool hasCard = rfid.PICC_IsNewCardPresent();
    if (!hasCard) {
      byte bufferATQA[2];
      byte bufferSize = sizeof(bufferATQA);
      if (rfid.PICC_WakeupA(bufferATQA, &bufferSize) == MFRC522::STATUS_OK) {
        hasCard = true;
      }
    }

    // 2. Baca serial kartu jika kartu terdeteksi
    if (hasCard && rfid.PICC_ReadCardSerial()) {
      String uidFormatted = "";
      String uidPlain = "";

      for (byte i = 0; i < rfid.uid.size; i++) {
        if (rfid.uid.uidByte[i] < 0x10) {
          uidFormatted += "0";
          uidPlain += "0";
        }
        uidFormatted += String(rfid.uid.uidByte[i], HEX);
        uidPlain += String(rfid.uid.uidByte[i], HEX);

        if (i < rfid.uid.size - 1) {
          uidFormatted += ":";
        }
      }
      uidFormatted.toUpperCase();
      uidPlain.toUpperCase();

      unsigned long currentMillis = millis();

      // Cooldown 800 ms agar responsif saat tap ulang
      if (uidPlain != lastScannedUID || (currentMillis - lastRFIDReadTime >= 800)) {
        lastScannedUID = uidPlain;
        lastRFIDReadTime = currentMillis;

        // Kirim UID hasil scan ke antrean sinkronisasi server Cloud Supabase
        if (xRFIDSyncQueue != NULL) {
          RFIDScanMessage scanMsg;
          memset(&scanMsg, 0, sizeof(scanMsg));
          strncpy(scanMsg.uid, uidPlain.c_str(), sizeof(scanMsg.uid) - 1);
          xQueueSend(xRFIDSyncQueue, &scanMsg, 0);
        }

        // Cek apakah perangkat sedang dalam Mode Registrasi Kartu dari Website/Cloud
        bool isRegMode = false;
        if (xSemaphoreTake(xDataMutex, portMAX_DELAY) == pdTRUE) {
          isRegMode = sharedRegistrationMode;
          xSemaphoreGive(xDataMutex);
        }

        if (isRegMode) {
          // ===================================================
          // MODE REGISTRASI: KARTU BARU DIREKAM UNTUK MEMBER
          // ===================================================
          if (xSemaphoreTake(xDataMutex, portMAX_DELAY) == pdTRUE) {
            sharedUID = uidPlain;
            sharedRegistrationMode = false; // Registrasi kartu selesai
            sharedRegCardCaptured = true;
            sharedAccessGranted = false;
            sharedAccessDeniedNoCar = false;
            sharedAccessDeniedSlotFull = false;
            rfidDisplayUntil = currentMillis + 3500; // Tampilkan status kartu tercatat 3.5 detik
            xSemaphoreGive(xDataMutex);
          }

          if (xSemaphoreTake(xSerialMutex, portMAX_DELAY) == pdTRUE) {
            Serial.println();
            Serial.println("========================================");
            Serial.println(" [REGISTRASI RFID] KARTU BARU TERCATAT! ");
            Serial.println("========================================");
            Serial.print("UID Kartu  : ");
            Serial.println(uidPlain);
            Serial.println("Status     : Berhasil disinkronkan ke Website!");
            Serial.println("Catatan    : Palang TIDAK dibuka (Mode Registrasi).");
            Serial.println("========================================");
            Serial.println();
            xSemaphoreGive(xSerialMutex);
          }

          // Bunyikan nada sukses registrasi (2 nada cerah)
          triggerBeep(2200, 100);
          vTaskDelay(pdMS_TO_TICKS(80));
          triggerBeep(2700, 150);

        } else {
          // ===================================================
          // MODE NORMAL PINTU GERBANG (KONTROL AKSES PARKIR)
          // ===================================================
          // Cek status mobil di gerbang dan sisa slot parkir yang tersedia
          bool carIsAtGate = false;
          int availableSlots = 0;
          if (xSemaphoreTake(xDataMutex, portMAX_DELAY) == pdTRUE) {
            carIsAtGate = sharedCarDetected;
            availableSlots = sharedAvailableCount;
            xSemaphoreGive(xDataMutex);
          }

          if (!carIsAtGate) {
            // ===================================================
            // KONDISI 1: TIDAK ADA MOBIL DI GERBANG -> DITOLAK
            // ===================================================
            if (xSemaphoreTake(xDataMutex, portMAX_DELAY) == pdTRUE) {
              sharedAccessGranted = false;
              sharedAccessDeniedNoCar = true;
              sharedAccessDeniedSlotFull = false;
              rfidDisplayUntil = currentMillis + 2000; // Tampilkan peringatan 2 detik
              xSemaphoreGive(xDataMutex);
            }

            if (xSemaphoreTake(xSerialMutex, portMAX_DELAY) == pdTRUE) {
              Serial.println();
              Serial.println("========================================");
              Serial.println("     [AKSES DITOLAK] TIDAK ADA MOBIL    ");
              Serial.println("========================================");
              Serial.println("Alasan : Kartu di-tap tapi tidak ada mobil di gerbang!");
              Serial.println("Aksi   : Dekatkan mobil ke sensor ultrasonic terlebih dahulu.");
              Serial.println("========================================");
              Serial.println();
              xSemaphoreGive(xSerialMutex);
            }

            triggerBeep(1000, 250); // Nada peringatan

          } else if (BLOCK_ENTRY_IF_FULL && availableSlots <= 0) {
            // ===================================================
            // KONDISI 2: ADA MOBIL TAPI SEMUA SLOT PENUH -> DITOLAK
            // ===================================================
            if (xSemaphoreTake(xDataMutex, portMAX_DELAY) == pdTRUE) {
              sharedAccessGranted = false;
              sharedAccessDeniedNoCar = false;
              sharedAccessDeniedSlotFull = true;
              rfidDisplayUntil = currentMillis + 2500; // Tampilkan status penuh 2.5 detik
              xSemaphoreGive(xDataMutex);
            }

            if (xSemaphoreTake(xSerialMutex, portMAX_DELAY) == pdTRUE) {
              Serial.println();
              Serial.println("========================================");
              Serial.println("     [AKSES DITOLAK] PARKIR PENUH!      ");
              Serial.println("========================================");
              Serial.println("Alasan : Semua 3 slot parkir telah terisi mobil!");
              Serial.println("Status : Palang gerbang TIDAK dibuka.");
              Serial.println("========================================");
              Serial.println();
              xSemaphoreGive(xSerialMutex);
            }

            triggerBeep(800, 350); // Nada error parkir penuh

          } else {
            // ===================================================
            // KONDISI 3: ADA MOBIL & MASIH ADA SLOT -> DITERIMA!
            // ===================================================
            if (xSemaphoreTake(xDataMutex, portMAX_DELAY) == pdTRUE) {
              sharedUID = uidPlain;
              sharedAccessGranted = true;
              sharedAccessDeniedNoCar = false;
              sharedAccessDeniedSlotFull = false;
              rfidDisplayUntil = currentMillis + 3000; // Tampilkan status sukses 3 detik
              xSemaphoreGive(xDataMutex);
            }

            if (xSemaphoreTake(xSerialMutex, portMAX_DELAY) == pdTRUE) {
              MFRC522::PICC_Type piccType = rfid.PICC_GetType(rfid.uid.sak);
              Serial.println();
              Serial.println("========================================");
              Serial.println("     [AKSES DITERIMA] SILAKAN MASUK     ");
              Serial.println("========================================");
              Serial.print("UID (Format) : ");
              Serial.println(uidFormatted);
              Serial.print("UID (Plain)  : ");
              Serial.println(uidPlain);
              Serial.print("Tipe Kartu   : ");
              Serial.println(rfid.PICC_GetTypeName(piccType));
              Serial.print("Sisa Slot    : ");
              Serial.print(availableSlots);
              Serial.println(" slot masih kosong");
              Serial.println("Status       : Palang Parkir Dibuka!");
              Serial.println("========================================");
              Serial.println();
              xSemaphoreGive(xSerialMutex);
            }

            // Bunyikan buzzer nada sukses (2500 Hz, 150 ms)
            triggerBeep(2500, 150);

            // Buka palang gerbang via TaskGate
            xSemaphoreGive(xGateOpenSemaphore);
          }
        }
      }

      // Hentikan komunikasi sementara dengan kartu
      rfid.PICC_HaltA();
    }

    // Polling RFID setiap 25 ms
    vTaskDelay(pdMS_TO_TICKS(25));
  }
}

// =====================================================
// RTOS TASK 5: LCD DISPLAY 16x2 (Berjalan di Core 1)
// =====================================================

void TaskLCD(void *pvParameters) {
  char line1[17];
  char line2[17];

  for (;;) {
    bool systemReady = false;
    String loadStatus = "Memuat...";
    bool carHere = false;
    bool s1 = true, s2 = true, s3 = true;
    int availCount = TOTAL_SLOTS;
    bool accessGranted = false;
    bool accessDeniedNoCar = false;
    bool accessDeniedSlotFull = false;
    bool accessDeniedPassback = false;
    String uid = "";
    bool isTempMessage = false;

    bool regMode = false;
    bool regCaptured = false;

    // Ambil data terbaru secara thread-safe
    if (xSemaphoreTake(xDataMutex, portMAX_DELAY) == pdTRUE) {
      systemReady = sharedSystemReady;
      loadStatus = sharedLoadingStatus;
      regMode = sharedRegistrationMode;
      regCaptured = sharedRegCardCaptured;
      carHere = sharedCarDetected;
      s1 = sharedSlot1Available;
      s2 = sharedSlot2Available;
      s3 = sharedSlot3Available;
      availCount = sharedAvailableCount;
      if (millis() < rfidDisplayUntil) {
        isTempMessage = true;
        accessGranted = sharedAccessGranted;
        accessDeniedNoCar = sharedAccessDeniedNoCar;
        accessDeniedSlotFull = sharedAccessDeniedSlotFull;
        accessDeniedPassback = sharedAccessDeniedPassback;
        uid = sharedUID;
      }
      xSemaphoreGive(xDataMutex);
    }

    if (!systemReady) {
      // 0. Tampilan Loading Animasi Selagi Sistem Belum Siap
      snprintf(line1, sizeof(line1), " MEMUAT SISTEM  ");
      static uint8_t animStep = 0;
      animStep = (animStep + 1) % 4;
      const char* dots[] = {".   ", "..  ", "... ", "...."};
      snprintf(line2, sizeof(line2), "%-12s%s", loadStatus.c_str(), dots[animStep]);
    } else if (regCaptured && isTempMessage) {
      // 1. Notifikasi Kartu Berhasil Direkam saat Mode Registrasi
      snprintf(line1, sizeof(line1), "KARTU TERCATAT! ");
      snprintf(line2, sizeof(line2), "ID:%-13s", uid.c_str());
    } else if (regMode) {
      // 2. Tampilan Mode Registrasi RFID Aktif dari Website
      snprintf(line1, sizeof(line1), "*REGISTRASI RFID*");
      static uint8_t regStep = 0;
      regStep = (regStep + 1) % 4;
      const char* dots[] = {".   ", "..  ", "... ", "...."};
      snprintf(line2, sizeof(line2), "TEMPEL KARTU%s", dots[regStep]);
    } else if (isTempMessage) {
      // 3. Pesan Notifikasi Sementara (Hasil Tap RFID Normal)
      if (accessGranted) {
        snprintf(line1, sizeof(line1), "AKSES DITERIMA! ");
        snprintf(line2, sizeof(line2), "ID:%-13s", uid.c_str());
      } else if (accessDeniedPassback) {
        snprintf(line1, sizeof(line1), "AKSES DITOLAK!  ");
        snprintf(line2, sizeof(line2), "ANTI-PASSBACK!  ");
      } else if (accessDeniedSlotFull) {
        snprintf(line1, sizeof(line1), "AKSES DITOLAK!  ");
        snprintf(line2, sizeof(line2), "PARKIR PENUH!   ");
      } else if (accessDeniedNoCar) {
        snprintf(line1, sizeof(line1), "AKSES DITOLAK!  ");
        snprintf(line2, sizeof(line2), "DEKATKAN MOBIL! ");
      }
    } else {
      // 2. Tampilan Standar Real-Time Sistem Smart Parking
      // Baris 1: Status 3 Slot Parkir ([1]=Kosong/Avail, [-]=Terisi) & Jumlah Sisa
      if (availCount == 0) {
        snprintf(line1, sizeof(line1), "[-][-][-] PENUH! ");
      } else {
        char c1 = s1 ? '1' : '-';
        char c2 = s2 ? '2' : '-';
        char c3 = s3 ? '3' : '-';
        snprintf(line1, sizeof(line1), "[%c][%c][%c] SISA:%d ", c1, c2, c3, availCount);
      }

      // Baris 2: Status Gerbang dari Sensor Ultrasonic
      if (carHere) {
        if (BLOCK_ENTRY_IF_FULL && availCount <= 0) {
          snprintf(line2, sizeof(line2), "PARKIR PENUH!   ");
        } else {
          snprintf(line2, sizeof(line2), "SILAKAN TAP...  ");
        }
      } else {
        snprintf(line2, sizeof(line2), "GERBANG: MAJU...");
      }
    }

    // Tulis ke LCD (16 karakter pas per baris, bebas kedipan / anti-flicker)
    lcd.setCursor(0, 0);
    lcd.print(line1);
    lcd.setCursor(0, 1);
    lcd.print(line2);

    // Refresh tampilan LCD setiap 250 ms
    vTaskDelay(pdMS_TO_TICKS(250));
  }
}

// =====================================================
// RTOS TASK 6: NETWORK & CLOUD SYNC (Berjalan di Core 0)
// =====================================================

void TaskNetwork(void *pvParameters) {
  vTaskDelay(pdMS_TO_TICKS(500)); // Beri waktu inisialisasi hardware stabil

  if (xSemaphoreTake(xSerialMutex, portMAX_DELAY) == pdTRUE) {
    Serial.println("[Network] Memulai modul WiFi ESP32...");
    Serial.print("[Network] Mencari & menghubungkan ke SSID: ");
    Serial.println(WIFI_SSID);
    xSemaphoreGive(xSerialMutex);
  }

  // Set status awal: Belum Siap (Menunggu WiFi)
  if (xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
    sharedSystemReady = false;
    sharedWiFiConnected = false;
    sharedLoadingStatus = "Konek WiFi";
    sharedLoadingProgress = 80;
    xSemaphoreGive(xDataMutex);
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long lastHeartbeat = 0;
  unsigned long lastSlotSync = 0;
  unsigned long lastSensorSync = 0;
  bool wasConnected = false;

  bool prevAvail1 = true;
  bool prevAvail2 = true;
  bool prevAvail3 = true;

  WiFiClientSecure client;
  client.setInsecure(); // Bypass validasi sertifikat CA agar hemat RAM pada ESP32

  for (;;) {
    // 1. CEK KONEKSI WIFI: Selagi WiFi BELUM connect, sistem BELUM SIAP!
    if (WiFi.status() != WL_CONNECTED) {
      if (wasConnected || xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
        sharedSystemReady = false;
        sharedWiFiConnected = false;
        sharedLoadingStatus = wasConnected ? "WiFi Putus" : "Konek WiFi";
        sharedLoadingProgress = 50;
        xSemaphoreGive(xDataMutex);
      }

      if (xSemaphoreTake(xSerialMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        Serial.printf("[Network] Menunggu koneksi WiFi ke '%s' (Sistem BELUM SIAP)...\n", WIFI_SSID);
        xSemaphoreGive(xSerialMutex);
      }

      wasConnected = false;
      WiFi.disconnect();
      WiFi.reconnect();
      vTaskDelay(pdMS_TO_TICKS(2000));
      continue;
    }

    // 2. TRANSISI: Jika WiFi baru saja berhasil terhubung (dari offline/boot ke connected)
    if (!wasConnected) {
      wasConnected = true;

      if (xSemaphoreTake(xSerialMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        Serial.println("[Network] WiFi Berhasil Terhubung!");
        Serial.printf("[Network] IP Address: %s\n", WiFi.localIP().toString().c_str());
        Serial.printf("[Network] RSSI Sinyal: %d dBm\n", WiFi.RSSI());
        xSemaphoreGive(xSerialMutex);
      }

      if (xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        sharedWiFiConnected = true;
        sharedLoadingStatus = "Cloud Siap!";
        sharedLoadingProgress = 100;
        xSemaphoreGive(xDataMutex);
      }

      // Berikan jeda 1.2 detik agar status konfirmasi Cloud Siap terbaca di layar LCD
      vTaskDelay(pdMS_TO_TICKS(1200));

      // Sistem RESMI SIAP beroperasi penuh karena WiFi & Cloud sudah terhubung!
      if (xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        sharedSystemReady = true;
        xSemaphoreGive(xDataMutex);
      }

      // Bunyikan nada buzzer sukses sistem siap (dua nada pendek ceria)
      triggerBeep(2000, 80);
      vTaskDelay(pdMS_TO_TICKS(100));
      triggerBeep(2700, 120);

      if (xSemaphoreTake(xSerialMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        Serial.println("[System] >>> WIFI TERHUBUNG: SISTEM SMART PARKING KINI RESMI SIAP BEROPERASI! <<<");
        xSemaphoreGive(xSerialMutex);
      }
    }

    // 0. JANGAN MULAI SINKRONISASI CLOUD APAPUN SEBELUM SISTEM RESMI SIAP!
    bool isSystemReadyNow = false;
    if (xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
      isSystemReadyNow = sharedSystemReady;
      xSemaphoreGive(xDataMutex);
    }
    if (!isSystemReadyNow) {
      vTaskDelay(pdMS_TO_TICKS(200));
      continue;
    }

    unsigned long currentMillis = millis();

    // 2. Cek Perintah / Status Mode Registrasi dari Cloud Setiap 1.0 Detik (Fast Sync)
    static unsigned long lastCmdCheck = 0;
    static unsigned long regModeStartTime = 0;
    if (currentMillis - lastCmdCheck >= 1000 || lastCmdCheck == 0) {
      lastCmdCheck = currentMillis;
      HTTPClient httpCmd;
      String cmdEndpoint = String(SUPABASE_URL) + "/rest/v1/iot_devices?device_id=eq." + String(DEVICE_ID) + "&select=status";
      if (httpCmd.begin(client, cmdEndpoint)) {
        httpCmd.addHeader("apikey", SUPABASE_KEY);
        httpCmd.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);
        int code = httpCmd.GET();
        if (code == 200) {
          String resp = httpCmd.getString();
          bool cloudWantsReg = (resp.indexOf("\"registering\"") > 0);
          bool wasReg = false;
          if (xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
            wasReg = sharedRegistrationMode;
            sharedRegistrationMode = cloudWantsReg;
            xSemaphoreGive(xDataMutex);
          }
          if (cloudWantsReg && !wasReg) {
            regModeStartTime = currentMillis;
            triggerBeep(2400, 100);
            vTaskDelay(pdMS_TO_TICKS(80));
            triggerBeep(2800, 150);
            if (xSemaphoreTake(xSerialMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
              Serial.println("[Cloud CMD] >>> DITERIMA: MODE REGISTRASI AKTIF DARI WEBSITE! <<<");
              Serial.println("[Cloud CMD] Silakan tempelkan kartu RFID pada reader alat (Gerbang tetap tertutup).");
              xSemaphoreGive(xSerialMutex);
            }
          }
        }
        httpCmd.end();
      }

      // Auto-Timeout Mode Registrasi (60 Detik) jika kartu tidak kunjung di-tap
      bool currentRegMode = false;
      if (xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
        currentRegMode = sharedRegistrationMode;
        xSemaphoreGive(xDataMutex);
      }
      if (currentRegMode && (currentMillis - regModeStartTime >= 60000) && regModeStartTime > 0) {
        if (xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
          sharedRegistrationMode = false;
          xSemaphoreGive(xDataMutex);
        }
        HTTPClient httpTimeout;
        String patchEndpoint = String(SUPABASE_URL) + "/rest/v1/iot_devices?device_id=eq." + String(DEVICE_ID);
        if (httpTimeout.begin(client, patchEndpoint)) {
          httpTimeout.addHeader("Content-Type", "application/json");
          httpTimeout.addHeader("apikey", SUPABASE_KEY);
          httpTimeout.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);
          httpTimeout.PATCH("{\"status\":\"online\",\"last_seen\":\"now()\"}");
          httpTimeout.end();
        }
        if (xSemaphoreTake(xSerialMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
          Serial.println("[Cloud CMD] Mode Registrasi TIMEOUT (60 detik). Kembali ke mode online.");
          xSemaphoreGive(xSerialMutex);
        }
      }
    }

    // 3. Sinkronisasi Kartu RFID yang Baru Saja Di-Tap (Queue Asinkron)
    RFIDScanMessage scanMsg;
    if (xQueueReceive(xRFIDSyncQueue, &scanMsg, 0) == pdTRUE) {
      HTTPClient http;
      String endpoint = String(SUPABASE_URL) + "/rest/v1/rfid_scans";
      if (http.begin(client, endpoint)) {
        http.addHeader("Content-Type", "application/json");
        http.addHeader("apikey", SUPABASE_KEY);
        http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);

        String payload = "{\"uid\":\"" + String(scanMsg.uid) + "\",\"device_id\":\"" + String(DEVICE_ID) + "\"}";
        int httpCode = http.POST(payload);
        if (xSemaphoreTake(xSerialMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
          Serial.printf("[Cloud] Sinkronisasi Scan RFID '%s' -> HTTP %d\n", scanMsg.uid, httpCode);
          xSemaphoreGive(xSerialMutex);
        }
        http.end();
      }

      // Jika kartu ini di-scan saat mode registrasi, reset status device kembali ke 'online'
      bool justReg = false;
      if (xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
        justReg = sharedRegCardCaptured;
        sharedRegCardCaptured = false;
        sharedRegistrationMode = false;
        xSemaphoreGive(xDataMutex);
      }
      if (justReg) {
        HTTPClient httpReset;
        String patchEndpoint = String(SUPABASE_URL) + "/rest/v1/iot_devices?device_id=eq." + String(DEVICE_ID);
        if (httpReset.begin(client, patchEndpoint)) {
          httpReset.addHeader("Content-Type", "application/json");
          httpReset.addHeader("apikey", SUPABASE_KEY);
          httpReset.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);
          String resetPayload = "{\"status\":\"online\",\"last_seen\":\"now()\"}";
          httpReset.PATCH(resetPayload);
          httpReset.end();
        }
      }
    }

    // 4. Kirim Heartbeat ke iot_devices Setiap 10 Detik
    if (currentMillis - lastHeartbeat >= 10000 || lastHeartbeat == 0) {
      lastHeartbeat = currentMillis;
      HTTPClient http;
      String endpoint = String(SUPABASE_URL) + "/rest/v1/iot_devices?on_conflict=device_id";
      if (http.begin(client, endpoint)) {
        http.addHeader("Content-Type", "application/json");
        http.addHeader("apikey", SUPABASE_KEY);
        http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);
        http.addHeader("Prefer", "resolution=merge-duplicates");

        bool isCurrentlyReg = false;
        if (xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
          isCurrentlyReg = sharedRegistrationMode;
          xSemaphoreGive(xDataMutex);
        }
        String devStatus = isCurrentlyReg ? "registering" : "online";
        String payload = "{\"device_id\":\"" + String(DEVICE_ID) + "\",\"status\":\"" + devStatus + "\",\"last_seen\":\"now()\"}";
        int httpCode = http.POST(payload);
        if (xSemaphoreTake(xSerialMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
          Serial.printf("[Cloud] Heartbeat '%s' -> HTTP %d\n", DEVICE_ID, httpCode);
          xSemaphoreGive(xSerialMutex);
        }
        http.end();
      }
    }

    // 4. Sinkronisasi Data 3 Slot Parkir ke parking_slots (P01, P02, P03)
    bool curAvail1 = true, curAvail2 = true, curAvail3 = true;
    int raw1 = 1, raw2 = 1, raw3 = 1;
    float curDistance = -1.0;
    if (xSemaphoreTake(xDataMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
      curAvail1 = sharedSlot1Available;
      curAvail2 = sharedSlot2Available;
      curAvail3 = sharedSlot3Available;
      raw1 = sharedRawIR1;
      raw2 = sharedRawIR2;
      raw3 = sharedRawIR3;
      curDistance = sharedDistance;
      xSemaphoreGive(xDataMutex);
    }

    bool slotChanged = (curAvail1 != prevAvail1 || curAvail2 != prevAvail2 || curAvail3 != prevAvail3);
    if (slotChanged || currentMillis - lastSlotSync >= 3000 || lastSlotSync == 0) {
      lastSlotSync = currentMillis;
      prevAvail1 = curAvail1;
      prevAvail2 = curAvail2;
      prevAvail3 = curAvail3;

      HTTPClient http;
      String endpoint = String(SUPABASE_URL) + "/rest/v1/parking_slots?on_conflict=slot_code";
      if (http.begin(client, endpoint)) {
        http.addHeader("Content-Type", "application/json");
        http.addHeader("apikey", SUPABASE_KEY);
        http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);
        http.addHeader("Prefer", "resolution=merge-duplicates");

        // Format batch payload untuk 3 slot parkir
        String payload = "[";
        payload += "{\"slot_code\":\"P01\",\"status\":\"" + String(curAvail1 ? "available" : "occupied") + "\",\"sensor_value\":" + String(raw1) + ",\"device_id\":\"" + String(DEVICE_ID) + "\",\"updated_at\":\"now()\"},";
        payload += "{\"slot_code\":\"P02\",\"status\":\"" + String(curAvail2 ? "available" : "occupied") + "\",\"sensor_value\":" + String(raw2) + ",\"device_id\":\"" + String(DEVICE_ID) + "\",\"updated_at\":\"now()\"},";
        payload += "{\"slot_code\":\"P03\",\"status\":\"" + String(curAvail3 ? "available" : "occupied") + "\",\"sensor_value\":" + String(raw3) + ",\"device_id\":\"" + String(DEVICE_ID) + "\",\"updated_at\":\"now()\"}";
        payload += "]";

        int httpCode = http.POST(payload);
        if (xSemaphoreTake(xSerialMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
          Serial.printf("[Cloud] Sync Status 3 Slot (P01-P03) -> HTTP %d\n", httpCode);
          xSemaphoreGive(xSerialMutex);
        }
        http.end();
      }
    }

    // 5. Sinkronisasi Data Jarak Ultrasonic ke sensor_data
    if (currentMillis - lastSensorSync >= 3000 || lastSensorSync == 0) {
      lastSensorSync = currentMillis;
      if (curDistance >= 0.0) {
        HTTPClient http;
        String endpoint = String(SUPABASE_URL) + "/rest/v1/sensor_data";
        if (http.begin(client, endpoint)) {
          http.addHeader("Content-Type", "application/json");
          http.addHeader("apikey", SUPABASE_KEY);
          http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);

          String payload = "{\"device_id\":\"" + String(DEVICE_ID) + "\",\"sensor_type\":\"ultrasonic\",\"sensor_value\":" + String(curDistance, 1) + "}";
          int httpCode = http.POST(payload);
          if (xSemaphoreTake(xSerialMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            Serial.printf("[Cloud] Sync Jarak Ultrasonic (%.1f cm) -> HTTP %d\n", curDistance, httpCode);
            xSemaphoreGive(xSerialMutex);
          }
          http.end();
        }
      }
    }

    vTaskDelay(pdMS_TO_TICKS(400));
  }
}

// =====================================================
// SETUP & BOOT LOADING
// =====================================================

// Helper animasi progress bar pada LCD 16x2 saat booting ESP32
void showBootLoading(const char* stepName, int percent) {
  lcd.setCursor(0, 0);
  lcd.print(" SMART PARKING  ");
  lcd.setCursor(0, 1);
  char buf[17];
  int bars = (percent * 7) / 100;
  char barStr[8];
  for (int i = 0; i < 7; i++) {
    barStr[i] = (i < bars) ? '=' : ' ';
  }
  barStr[7] = '\0';
  snprintf(buf, sizeof(buf), "%-7s [%s]", stepName, barStr);
  lcd.print(buf);
  Serial.printf("[Boot Loading] %s (%d%%)\n", stepName, percent);
}

void setup() {
  Serial.begin(115200);
  delay(300);

  // Inisialisasi I2C kustom untuk LCD 16x2 (SDA: GPIO 16, SCL: GPIO 17)
  Wire.begin(LCD_SDA_PIN, LCD_SCL_PIN);
  lcd.init();
  lcd.backlight();
  showBootLoading("Init HW", 20);
  delay(200);

  // Inisialisasi Mutex & Queue
  xSerialMutex = xSemaphoreCreateMutex();
  xDataMutex = xSemaphoreCreateMutex();
  xBuzzerQueue = xQueueCreate(5, sizeof(BuzzerMessage));
  xRFIDSyncQueue = xQueueCreate(5, sizeof(RFIDScanMessage));
  xGateOpenSemaphore = xSemaphoreCreateBinary();

  // Inisialisasi pin Buzzer
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);

  // Inisialisasi pin Ultrasonic
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);

  // Inisialisasi pin Sensor IR 3 Slot Parkir
  pinMode(PIN_IR_SLOT1, INPUT_PULLUP);
  pinMode(PIN_IR_SLOT2, INPUT_PULLUP);
  pinMode(PIN_IR_SLOT3, INPUT); // GPIO 35 adalah input-only, modul IR sudah memiliki pull-up onboard

  showBootLoading("InitSPI", 45);
  delay(150);

  // Inisialisasi SPI & RFID RC522
  SPI.begin(
    RFID_SCK,
    RFID_MISO,
    RFID_MOSI,
    RFID_SS
  );

  rfid.PCD_Init();
  delay(50);
  rfid.PCD_AntennaOn(); // Pastikan pemancar RF TX1 & TX2 aktif bertenaga penuh
  rfid.PCD_SetAntennaGain(rfid.RxGain_max); // Atur sensitivitas antena ke maksimum (48 dB)

  showBootLoading("RFID OK", 70);
  delay(150);

  Serial.println();
  Serial.println("========================================");
  Serial.println(" SMART PARKING SYSTEM (ESP32 FreeRTOS)  ");
  Serial.println(" Fitur: Gerbang Ultrasonic + RFID + Servo");
  Serial.println("        + 3 Slot IR Parkir + LCD 16x2   ");
  Serial.println("        + WiFi Cloud Sync (Supabase)    ");
  Serial.println("========================================");
  Serial.print("Status Modul RFID: ");
  rfid.PCD_DumpVersionToSerial();

  byte ver = rfid.PCD_ReadRegister(rfid.VersionReg);
  if (ver == 0x00 || ver == 0xFF) {
    Serial.println("[PERINGATAN] Modul RC522 TIDAK terhubung dengan benar!");
  } else {
    Serial.println("[OK] Modul RC522 terhubung dan siap membaca kartu!");
  }
  Serial.println("========================================");

  showBootLoading("RTOS...", 85);
  delay(150);

  // ---------------------------------------------------
  // PEMBUATAN TASK FREERTOS (Multi-core ESP32)
  // ---------------------------------------------------

  // Task Buzzer: Prioritas 1, Core 1
  xTaskCreatePinnedToCore(
    TaskBuzzer,
    "TaskBuzzer",
    2048,
    NULL,
    1,
    NULL,
    1
  );

  // Task Gate Servo: Prioritas 1, Core 1
  xTaskCreatePinnedToCore(
    TaskGate,
    "TaskGate",
    2048,
    NULL,
    1,
    NULL,
    1
  );

  // Task Sensors (Ultrasonic & 3 Slot IR): Prioritas 1, Core 0
  xTaskCreatePinnedToCore(
    TaskSensors,
    "TaskSensors",
    3072,
    NULL,
    1,
    NULL,
    0
  );

  // Task RFID: Prioritas 2, Core 1 (Validasi Akses)
  xTaskCreatePinnedToCore(
    TaskRFID,
    "TaskRFID",
    4096,
    NULL,
    2,
    NULL,
    1
  );

  // Task LCD: Prioritas 1, Core 1 (User Interface)
  xTaskCreatePinnedToCore(
    TaskLCD,
    "TaskLCD",
    3072,
    NULL,
    1,
    NULL,
    1
  );

  // Task Network: Prioritas 1, Core 0 (Sinkronisasi Cloud Supabase)
  xTaskCreatePinnedToCore(
    TaskNetwork,
    "TaskNetwork",
    8192,
    NULL,
    1,
    NULL,
    0
  );

  if (xSemaphoreTake(xSerialMutex, portMAX_DELAY) == pdTRUE) {
    Serial.println();
    Serial.println("========================================================");
    Serial.println(" [BOOT] Hardware Terpasang & Seluruh Task RTOS Aktif.   ");
    Serial.println(" [BOOT] SELURUH SENSOR (Ultrasonic, IR, RFID) DIKUNCI!  ");
    Serial.println("        Sensor TIDAK akan membaca apapun sebelum sistem ");
    Serial.println("        siap & terhubung ke WiFi / Cloud Supabase.      ");
    Serial.println("========================================================");
    Serial.println();
    xSemaphoreGive(xSerialMutex);
  }

  delay(500); // Jeda transisi boot
}

// =====================================================
// LOOP
// =====================================================

void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}