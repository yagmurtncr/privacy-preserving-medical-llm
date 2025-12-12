#!/bin/bash
# ============================================================
# HTTPS/TLS Sertifika Kurulum Script
# ============================================================

echo "🔐 HTTPS/TLS Sertifika Kurulumu"
echo "================================"
echo ""

# SSL dizini oluştur
mkdir -p ssl

# Sertifika türü seç
echo "Hangi sertifika türünü kullanmak istersiniz?"
echo ""
echo "1) Self-Signed Certificate (Test/Development için)"
echo "2) Let's Encrypt (Production için - domain gerekli)"
echo ""
read -p "Seçiminiz (1 veya 2): " CERT_TYPE

if [ "$CERT_TYPE" = "1" ]; then
    echo ""
    echo "📝 Self-Signed Sertifika Oluşturuluyor..."
    echo ""
    
    # OpenSSL ile self-signed sertifika oluştur
    openssl req -x509 -newkey rsa:4096 -nodes \
        -keyout ssl/server_key.pem \
        -out ssl/server_cert.pem \
        -days 365 \
        -subj "/C=TR/ST=Istanbul/L=Istanbul/O=Hospital/CN=localhost"
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Self-signed sertifika oluşturuldu!"
        echo "   Sertifika: ssl/server_cert.pem"
        echo "   Key: ssl/server_key.pem"
        echo "   Geçerlilik: 365 gün"
        echo ""
        echo "⚠️  NOT: Self-signed sertifika tarayıcılarda 'Güvenli Değil' uyarısı verir."
        echo "   Production için Let's Encrypt kullanın!"
        echo ""
        
        # .env dosyasını güncelle
        if grep -q "ENABLE_HTTPS" .env; then
            sed -i 's/ENABLE_HTTPS=false/ENABLE_HTTPS=true/' .env
            echo "✅ .env dosyası güncellendi (ENABLE_HTTPS=true)"
        fi
        
        echo ""
        echo "🚀 Server'ı başlatmak için:"
        echo "   CUDA_VISIBLE_DEVICES=3 python3 heaan_encrypted/server/hybrid_gpu_server.py \\"
        echo "       --ssl-keyfile ssl/server_key.pem \\"
        echo "       --ssl-certfile ssl/server_cert.pem"
        echo ""
    else
        echo "❌ Sertifika oluşturulamadı!"
        exit 1
    fi

elif [ "$CERT_TYPE" = "2" ]; then
    echo ""
    echo "📝 Let's Encrypt Sertifika Kurulumu"
    echo ""
    
    # Domain adı iste
    read -p "Domain adınızı girin (örn: api.hospital.com): " DOMAIN
    
    if [ -z "$DOMAIN" ]; then
        echo "❌ Domain adı gerekli!"
        exit 1
    fi
    
    # Certbot kurulu mu kontrol et
    if ! command -v certbot &> /dev/null; then
        echo "⚠️  Certbot bulunamadı! Kuruluyor..."
        sudo apt update
        sudo apt install -y certbot
    fi
    
    echo ""
    echo "🔧 Certbot ile sertifika alınıyor..."
    echo "   Domain: $DOMAIN"
    echo ""
    
    # Certbot standalone mode
    sudo certbot certonly --standalone -d "$DOMAIN"
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Let's Encrypt sertifikası alındı!"
        echo "   Sertifika: /etc/letsencrypt/live/$DOMAIN/fullchain.pem"
        echo "   Key: /etc/letsencrypt/live/$DOMAIN/privkey.pem"
        echo ""
        
        # .env dosyasını güncelle
        if grep -q "ENABLE_HTTPS" .env; then
            sed -i 's/ENABLE_HTTPS=false/ENABLE_HTTPS=true/' .env
            sed -i 's/ENVIRONMENT=development/ENVIRONMENT=production/' .env
            echo "✅ .env dosyası güncellendi (ENABLE_HTTPS=true, ENVIRONMENT=production)"
        fi
        
        echo ""
        echo "🚀 Server'ı başlatmak için:"
        echo "   sudo CUDA_VISIBLE_DEVICES=3 python3 heaan_encrypted/server/hybrid_gpu_server.py \\"
        echo "       --ssl-keyfile /etc/letsencrypt/live/$DOMAIN/privkey.pem \\"
        echo "       --ssl-certfile /etc/letsencrypt/live/$DOMAIN/fullchain.pem"
        echo ""
        echo "📅 Otomatik yenileme için crontab ekleyin:"
        echo "   0 0 * * * certbot renew --quiet"
        echo ""
    else
        echo "❌ Let's Encrypt sertifikası alınamadı!"
        echo "   Port 80'in açık olduğundan emin olun."
        exit 1
    fi

else
    echo "❌ Geçersiz seçim!"
    exit 1
fi

echo "✅ HTTPS kurulumu tamamlandı!"

