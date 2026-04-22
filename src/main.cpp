// ===== ESP32 HUZZAH32 (Feather): DS18B20 + LCD (I2C) + Wi-Fi TCP server =====
// Pinout HUZZAH32:
//   I2C SDA -> GPIO23, I2C SCL -> GPIO22
//   DS18B20 DQ -> GPIO4  (VCC -> 3V3, GND -> GND, 4.7kΩ między DQ a 3V3)
// LCD 16x2 I2C: domyślny adres 0x27 (jeśli masz 0x3F, zmień poniżej)

#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ===== Piny / adresy =====
#define I2C_SDA      23       // HUZZAH32 I2C SDA
#define I2C_SCL      22       // HUZZAH32 I2C SCL
#define ONE_WIRE_BUS 21       // DS18B20 DQ -> GPIO21
#define LCD_ADDR     0x27     // zmień na 0x3F jeśli Twój moduł tak ma
#define LCD_COLS     16
#define LCD_ROWS     2

// ===== Wi-Fi / TCP =====
const char* WIFI_SSID = "PLAY_Swiatlowodowy_1626";
const char* WIFI_PASS = "j$5G41C&hAGB";
const uint16_t TCP_PORT = 3333;
WiFiServer server(TCP_PORT);

// ===== Interwały =====
const unsigned long intervalMsTx   = 1000; // wysyłka po TCP
const unsigned long intervalMsLCD  = 500;  // odświeżanie LCD
const unsigned long dsConvMs       = 200;  // czas konwersji DS18B20 (12-bit)

unsigned long tLastTx  = 0;
unsigned long tLastLCD = 0;

// ===== Obiekty =====
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);

float lastT = NAN;

// ===== Pomocnicze =====
void printCentered(uint8_t row, const String& s) {
  String line = s;
  if (line.length() < LCD_COLS) {
    int pad = (LCD_COLS - line.length()) / 2;
    line = String(' ', pad) + line;
  }
  lcd.setCursor(0, row);
  lcd.print(line.substring(0, LCD_COLS));
}

void lcdShow2Lines(const String& l1, const String& l2) {
  lcd.setCursor(0, 0); lcd.print("                ");
  lcd.setCursor(0, 1); lcd.print("                ");
  lcd.setCursor(0, 0); lcd.print(l1.substring(0, 16));
  lcd.setCursor(0, 1); lcd.print(l2.substring(0, 16));
}

// Odczyt temperatury z DS18B20 (2 próby, filtr błędów 85°C / NaN / zakres)
float readTemperature() {
  sensors.requestTemperatures();
  delay(dsConvMs);
  float t1 = sensors.getTempCByIndex(0);
  if (t1 == 85.0f || t1 < -50.0f || t1 > 125.0f || isnan(t1)) {
    sensors.requestTemperatures();
    delay(dsConvMs);
    float t2 = sensors.getTempCByIndex(0);
    if (t2 == 85.0f || t2 < -50.0f || t2 > 125.0f || isnan(t2)) {
      return NAN;
    }
    return t2;
  }
  return t1;
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  lcdShow2Lines("Laczenie z WiFi", WIFI_SSID);
  Serial.print("Łączenie z Wi-Fi");

  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    Serial.print(".");
    delay(500);
    if (millis() - t0 > 20000) {
      Serial.println("\nTimeout Wi-Fi. Reset...");
      lcdShow2Lines("WiFi timeout", "Reset...");
      delay(500);
      ESP.restart();
    }
  }
  IPAddress ip = WiFi.localIP();
  Serial.print("\nPołączono. IP: ");
  Serial.println(ip);
  lcdShow2Lines("WiFi OK", "IP: " + ip.toString());
}

void setup() {
  Serial.begin(115200);
  delay(200);

  // I2C + LCD (HUZZAH32: SDA=23, SCL=22)
  Wire.begin(I2C_SDA, I2C_SCL);
  lcd.init();
  lcd.backlight();
  printCentered(0, "Start LCD + DS18B20");
  printCentered(1, "Prosze czekac...");
  delay(500);

  // DS18B20
  sensors.begin();
  int n = sensors.getDeviceCount();
  Serial.printf("Znaleziono %d czujnik(ow) DS18B20\n", n);

  // Wi-Fi + TCP
  connectWiFi();
  server.begin();
  // REMOVED: server.setNoDelay(true);
  lcdShow2Lines("Serwer TCP:", WiFi.localIP().toString() + ":" + String(TCP_PORT));
  Serial.printf("Serwer TCP nasłuchuje na %s:%u\n",
                WiFi.localIP().toString().c_str(), TCP_PORT);

  delay(500);
  lcd.clear();
  printCentered(0, "Temp [C]:");
}

void loop() {
  // podtrzymaj Wi-Fi
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  // jeden klient TCP naraz
  static WiFiClient client;
  if (!client || !client.connected()) {
    client = server.available();
  }

  unsigned long now = millis();

  // Wysyłka po TCP
  if (client && client.connected() && (now - tLastTx >= intervalMsTx)) {
    tLastTx = now;
    float t = readTemperature();
    if (isnan(t)) {
      client.printf("T=nan\n");
      Serial.println("TX: T=nan");
    } else {
      client.printf("T=%.2f\n", t);
      Serial.printf("TX: T=%.2f\n", t);
      lastT = t;
    }
  }

  // LCD
  if (now - tLastLCD >= intervalMsLCD) {
    tLastLCD = now;
    String top = isnan(lastT) ? "T: --- C" : ("T: " + String(lastT, 2) + " C");
    String bottom = WiFi.localIP().toString() + ":" + String(TCP_PORT);
    lcdShow2Lines(top, bottom);
  }
}