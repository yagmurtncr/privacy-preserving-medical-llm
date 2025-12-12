#!/bin/bash

# 🧪 Manuel Test Script - HE-with-LLM Server
# Server başladıktan sonra bu script'i çalıştır!

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                                                                      ║"
echo "║            🧪 HE-WITH-LLM MANUEL TEST                                ║"
echo "║                                                                      ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Renkler
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Server URL
SERVER_URL="https://localhost:9200"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 ADIM 1: HEALTH CHECK"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

curl -k -s $SERVER_URL/ | python3 -m json.tool
HEALTH_STATUS=$?

if [ $HEALTH_STATUS -eq 0 ]; then
    echo -e "\n${GREEN}✅ Server çalışıyor!${NC}\n"
else
    echo -e "\n${RED}❌ Server çalışmıyor! Önce başlat:${NC}"
    echo "   cd /mnt/development/ubuntu/nytuncer/he-with-llm"
    echo "   python3 heaan_encrypted/server/hybrid_gpu_server.py"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔐 ADIM 2: LOGIN - TOKEN AL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${YELLOW}Username: yagmur${NC}"
echo -e "${YELLOW}Password: yagmur123${NC}"
echo ""

TOKEN_RESPONSE=$(curl -k -s -X POST $SERVER_URL/login \
  -H "Content-Type: application/json" \
  -d '{"username":"yagmur","password":"yagmur123"}')

echo "$TOKEN_RESPONSE" | python3 -m json.tool

TOKEN=$(echo $TOKEN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo -e "\n${RED}❌ Token alınamadı!${NC}"
    exit 1
fi

echo -e "\n${GREEN}✅ Token alındı!${NC}"
echo ""

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧪 ADIM 3: TEST ÖRNEKLERİ (5 Gerçek Labaratuvar Vakası)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Test 1: Demir Eksikliği Anemisi
echo -e "${BLUE}TEST 1: Demir Eksikliği Anemisi${NC}"
echo "────────────────────────────────────────────────────────────"
echo ""

curl -k -s -X POST $SERVER_URL/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Zeynep Arslan, 28 yaş, TC: 11223344556. Hemogram: RBC 3.2 (düşük), Hemoglobin 9.8 g/dL (düşük), MCV 68 fL (düşük), Ferritin 8 ng/mL (çok düşük). Tanı ve tedavi öner.",
    "max_new_tokens": 256,
    "temperature": 0.2,
    "enable_pii_protection": true
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('✅ Response:', data['response'][:200] + '...')
print('⏱️  Süre:', data['processing_time_s'], 's')
print('🔐 Encryption:', 'Aktif' if data['model_encrypted_in_memory'] else 'Pasif')
print('🎭 PII Detected:', data['pii_detected'])
"

echo ""
echo "Devam etmek için Enter'a bas..."
read

# Test 2: Kronik Böbrek Hastalığı
echo ""
echo -e "${BLUE}TEST 2: Kronik Böbrek Hastalığı${NC}"
echo "────────────────────────────────────────────────────────────"
echo ""

curl -k -s -X POST $SERVER_URL/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Ali Yılmaz, 62 yaş, TC: 22334455667, Tel: 05441234567. Böbrek fonksiyon testleri: Kreatinin 3.8 mg/dL (yüksek), eGFR 28 mL/dk/1.73m² (çok düşük), BUN 48 mg/dL (yüksek), Potasyum 5.9 mEq/L (yüksek). Tanı ve tedavi öner.",
    "max_new_tokens": 256,
    "temperature": 0.2,
    "enable_pii_protection": true
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('✅ Response:', data['response'][:200] + '...')
print('⏱️  Süre:', data['processing_time_s'], 's')
print('🎭 PII Detected:', data['pii_detected'])
"

echo ""
echo "Devam etmek için Enter'a bas..."
read

# Test 3: Tip 2 Diyabet
echo ""
echo -e "${BLUE}TEST 3: Tip 2 Diyabet (Hafif Örnek)${NC}"
echo "────────────────────────────────────────────────────────────"
echo ""

curl -k -s -X POST $SERVER_URL/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Elif Demir, 45 yaş. HbA1c %7.8 (yüksek), Açlık kan şekeri 156 mg/dL (yüksek). Tanı ve öneriler?",
    "max_new_tokens": 128,
    "temperature": 0.2,
    "enable_pii_protection": true
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('✅ Response:', data['response'][:200] + '...')
print('⏱️  Süre:', data['processing_time_s'], 's')
print('🎭 PII Detected:', data['pii_detected'])
"

echo ""
echo "Devam etmek için Enter'a bas..."
read

# Test 4: Hipertansiyon
echo ""
echo -e "${BLUE}TEST 4: Hipertansiyon${NC}"
echo "────────────────────────────────────────────────────────────"
echo ""

curl -k -s -X POST $SERVER_URL/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Mehmet Kaya, 58 yaş, TC: 33445566778. Vital bulgular: Tansiyon 165/98 mmHg (yüksek), Kalp hızı 88/dk. Lipid paneli: Total Kolesterol 245 mg/dL (yüksek), LDL 168 mg/dL (yüksek), HDL 38 mg/dL (düşük), Trigliserit 210 mg/dL (yüksek). Tanı ve tedavi yaklaşımı?",
    "max_new_tokens": 256,
    "temperature": 0.2,
    "enable_pii_protection": true
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('✅ Response:', data['response'][:200] + '...')
print('⏱️  Süre:', data['processing_time_s'], 's')
print('🔐 Encryption:', 'Aktif' if data['model_encrypted_in_memory'] else 'Pasif')
print('🎭 PII Detected:', data['pii_detected'])
"

echo ""
echo "Devam etmek için Enter'a bas..."
read

# Test 5: Hipotiroidizm
echo ""
echo -e "${BLUE}TEST 5: Hipotiroidizm${NC}"
echo "────────────────────────────────────────────────────────────"
echo ""

curl -k -s -X POST $SERVER_URL/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Ayşe Şahin, 35 yaş, Tel: 05331234567. Tiroid fonksiyon testleri: TSH 8.9 mIU/L (yüksek), Serbest T4 0.7 ng/dL (düşük), Serbest T3 1.8 pg/mL (düşük), Anti-TPO 450 IU/mL (yüksek). Şikayetler: Yorgunluk, kilo alımı, saç dökülmesi. Tanı ve tedavi?",
    "max_new_tokens": 256,
    "temperature": 0.2,
    "enable_pii_protection": true
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('✅ Response:', data['response'][:200] + '...')
print('⏱️  Süre:', data['processing_time_s'], 's')
print('🔐 Encryption:', 'Aktif' if data['model_encrypted_in_memory'] else 'Pasif')
print('🎭 PII Detected:', data['pii_detected'])
"

echo ""
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ TESTLER TAMAMLANDI!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo ""
echo "📊 Daha fazla test için:"
echo "   • Swagger UI: https://localhost:9200/docs"
echo "   • QUICK_START.md'deki 6. örnek: B12 Vitamini Eksikliği"
echo "   • Kendi gerçek verilerini test et!"
echo ""

