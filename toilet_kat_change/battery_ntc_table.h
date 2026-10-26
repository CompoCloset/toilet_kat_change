// Battery pack NTC center curve. R25 = 10 kΩ, B25/50 = 3950 K.
// Values are kilohms at each integer °C from -40 to 105 (center column).
#ifndef BATTERY_NTC_TABLE_H
#define BATTERY_NTC_TABLE_H

#include <math.h>

constexpr int kBattNtcTempMinC = -40;
constexpr int kBattNtcTempMaxC = 105;
constexpr int kBattNtcTableLen = kBattNtcTempMaxC - kBattNtcTempMinC + 1;

// Index 0 is -40 °C. Index (25 - kBattNtcTempMinC) is 25 °C = 10 kΩ.
static const float kBattNtcCenterKohm[kBattNtcTableLen] = {
  343.6326f, 321.2809f, 300.5339f, 281.2660f, 263.3624f, 246.7177f, 231.2355f, 216.8273f, 203.4118f, 190.9144f,
  179.2666f, 168.4053f, 158.2726f, 148.8151f, 139.9837f, 131.7332f, 124.0216f, 116.8107f, 110.0648f, 103.7512f,
  97.8396f, 92.3020f, 87.1124f, 82.2471f, 77.6837f, 73.4018f, 69.3823f, 65.6077f, 62.0616f, 58.7288f,
  55.5953f, 52.6480f, 49.8747f, 47.2643f, 44.8062f, 42.4906f, 40.3086f, 38.2516f, 36.3117f, 34.4817f,
  32.7547f, 31.1243f, 29.5847f, 28.1301f, 26.7556f, 25.4562f, 24.2274f, 23.0650f, 21.9650f, 20.9239f,
  19.9380f, 19.0041f, 18.1193f, 17.2807f, 16.4857f, 15.7317f, 15.0164f, 14.3376f, 13.6933f, 13.0816f,
  12.5005f, 11.9485f, 11.4239f, 10.9252f, 10.4510f, 10.0000f, 9.5709f, 9.1626f, 8.7738f, 8.4037f,
  8.0512f, 7.7154f, 7.3953f, 7.0903f, 6.7995f, 6.5221f, 6.2576f, 6.0051f, 5.7642f, 5.5342f,
  5.3146f, 5.1049f, 4.9045f, 4.7130f, 4.5300f, 4.3551f, 4.1878f, 4.0278f, 3.8748f, 3.7283f,
  3.5882f, 3.4540f, 3.3255f, 3.2025f, 3.0846f, 2.9717f, 2.8635f, 2.7597f, 2.6603f, 2.5649f,
  2.4734f, 2.3856f, 2.3014f, 2.2206f, 2.1431f, 2.0686f, 1.9970f, 1.9283f, 1.8623f, 1.7989f,
  1.7380f, 1.6794f, 1.6231f, 1.5689f, 1.5168f, 1.4667f, 1.4185f, 1.3722f, 1.3275f, 1.2845f,
  1.2431f, 1.2033f, 1.1649f, 1.1279f, 1.0923f, 1.0580f, 1.0249f, 0.9930f, 0.9623f, 0.9326f,
  0.9040f, 0.8764f, 0.8498f, 0.8241f, 0.7994f, 0.7754f, 0.7523f, 0.7300f, 0.7085f, 0.6877f,
  0.6676f, 0.6482f, 0.6295f, 0.6113f, 0.5938f, 0.5769f
};

inline float batteryTempCAtTableIndex(int coldIndex, float resistanceKohm) {
  float rHi = kBattNtcCenterKohm[coldIndex];
  float rLo = kBattNtcCenterKohm[coldIndex + 1];
  float logHi = logf(rHi);
  float logLo = logf(rLo);
  float denom = logHi - logLo;
  float frac = (denom == 0.0f) ? 0.0f : (logHi - logf(resistanceKohm)) / denom;
  return (float)(kBattNtcTempMinC + coldIndex) + frac;
}

// Log-R interpolation between 1 °C points. Slightly outside the table is
// extrapolated from the end segment. Returns false when that lands past
// -45 °C or 110 °C (open, short, or a divider that does not match this NTC).
inline bool batteryTempCFromKohm(float resistanceKohm, float* tempC) {
  if (tempC == nullptr || !(resistanceKohm > 0.0f)) {
    return false;
  }

  if (resistanceKohm >= kBattNtcCenterKohm[0]) {
    float temp = batteryTempCAtTableIndex(0, resistanceKohm);
    *tempC = temp;
    return temp >= -45.0f;
  }
  if (resistanceKohm <= kBattNtcCenterKohm[kBattNtcTableLen - 1]) {
    float temp = batteryTempCAtTableIndex(kBattNtcTableLen - 2, resistanceKohm);
    *tempC = temp;
    return temp <= 110.0f;
  }
  for (int i = 0; i < kBattNtcTableLen - 1; i++) {
    if (resistanceKohm <= kBattNtcCenterKohm[i] && resistanceKohm >= kBattNtcCenterKohm[i + 1]) {
      *tempC = batteryTempCAtTableIndex(i, resistanceKohm);
      return true;
    }
  }
  return false;
}

#endif
