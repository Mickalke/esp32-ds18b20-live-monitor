// ESP32 HUZZAH32: DS18B20 + LCD (I2C) + Wi-Fi TCP server
// DS18B20 DQ -> GPIO21, 4.7kOhm pull-up to 3V3
// LCD I2C: SDA->GPIO23, SCL->GPIO22

#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "secrets.h"

#define I2C_SDA      23
#define I2C_SCL      22
#define ONE_WIRE_BUS 21
#define LCD_ADDR     0x27
#define LCD_COLS     16
#define LCD_ROWS      2

const uint16_t TCP_PORT = 3333;
WiFiServer server(TCP_PORT);

const unsigned long intervalMsTx  = 1000;
const unsigned long intervalMsLCD =  500;
const unsigned long dsConvMs      =  200;

unsigned long tLastTx  = 0;
unsigned long tLastLCD = 0;

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);
float lastT = NAN;

void lcdShow2Lines(const String& l1, const String& l2) {
  lcd.setCursor(0,0); lcd.print("                ");
  lcd.setCursor(0,1); lcd.print("                ");
  lcd.setCursor(0,0); lcd.print(l1.substring(0,16));
  lcd.setCursor(0,1); lcd.print(l2.substring(0,16));
}

float readTemperature() {
  sensors.requestTemperatures(); delay(dsConvMs);
  float t = sensors.getTempCByIndex(0);
  if (t == 85.0f || t < -50.0f || t > 125.0f || isnan(t)) {
    sensors.requestTemperatures(); delay(dsConvMs);
    t = sensors.getTempCByIndex(0);
    if (t == 85.0f || t < -50.0f || t > 125.0f || isnan(t)) return NAN;
  }
  return t;
}

void connectWiFi() {
  WiFi.mode(WIFI_STA); WiFi.begin(WIFI_SSID, WIFI_PASS);
  lcdShow2Lines("Laczenie z WiFi", WIFI_SSID);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    if (millis() - t0 > 20000) { lcdShow2Lines("WiFi timeout","Reset..."); delay(500); ESP.restart(); }
  }
  lcdShow2Lines("WiFi OK", "IP: " + WiFi.localIP().toString());
}

void setup() {
  Serial.begin(115200); delay(200);
  Wire.begin(I2C_SDA, I2C_SCL);
  lcd.init(); lcd.backlight();
  lcdShow2Lines("Start...", ""); delay(500);
  sensors.begin();
  connectWiFi();
  server.begin();
  lcdShow2Lines("TCP:", WiFi.localIP().toString() + ":" + String(TCP_PORT));
  delay(1000); lcd.clear();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  static WiFiClient client;
  if (!client || !client.connected()) client = server.available();
  unsigned long now = millis();
  if (client && client.connected() && (now - tLastTx >= intervalMsTx)) {
    tLastTx = now;
    float t = readTemperature();
    if (isnan(t)) client.printf("T=nan\n");
    else { client.printf("T=%.2f\n", t); lastT = t; }
  }
  if (now - tLastLCD >= intervalMsLCD) {
    tLastLCD = now;
    lcdShow2Lines(isnan(lastT) ? "T: --- C" : "T: " + String(lastT,2) + " C",
                  WiFi.localIP().toString() + ":" + String(TCP_PORT));
  }
}
