# BAP Çıktı Yönetim Sistemi — Kurulum Kılavuzu

## Gereksinimler
- Docker & Docker Compose (IT'ye söyleyin, standart kurulum)
- Python 3.12+ (yerel geliştirme için)

---

## 1. Hızlı Başlangıç (Docker ile)

```bash
# Projeyi sunucuya kopyalayın
git clone ... veya zip'i açın

# .env dosyasını oluşturun
cp .env.example .env
# .env'i düzenleyip güçlü şifreler yazın!

# Başlatın
docker compose up -d

# Kontrol edin
docker compose logs -f web
```

Sistem http://sunucu-ip:8000 adresinde çalışacak.

**İlk giriş:** admin / Admin2024!  
⚠️ İlk girişten sonra şifreyi değiştirin.

---

## 2. İlk Adımlar

### Proje listesini yükleyin
1. Admin panele girin: /yonetim
2. "Proje Yükle" menüsüne gidin
3. Excel/CSV dosyanızı yükleyin
4. Sistem projeleri ve hoca hesaplarını otomatik oluşturur

### Hocalara bildirin
Her hoca için oluşturulan kullanıcı adı: `ad.soyad` (emailden türetilir)  
Varsayılan şifre: `Bap2024!` (yükleme sırasında belirttiğiniz)

Hocalara gönderilecek link: `http://sunucu-ip:8000/giris`

---

## 3. LDAP Entegrasyonu (BT'den bilgi gelince)

.env dosyasında şu değerleri güncelleyin:
```
LDAP_ENABLED=true
LDAP_HOST=ldap.universite.edu.tr
LDAP_PORT=389
LDAP_BASE_DN=dc=universite,dc=edu,dc=tr
LDAP_BIND_DN=cn=bap-service,ou=services,dc=universite,dc=edu,dc=tr
LDAP_BIND_PASSWORD=ldap_servis_sifresi
```

Sonra:
```bash
docker compose restart web
```

LDAP aktif olunca hocalar kurumsal kullanıcı adı/şifresiyle doğrudan giriş yapabilir.  
Sistemde hesabı yoksa ilk girişte otomatik oluşturulur.

---

## 4. Rapor Alma

Admin panelden:
- **PDF:** Yöneticinize sunabileceğiniz formatlı rapor (çıktı sayıları, grafikler, proje listesi)
- **Excel:** Tüm verilerin detaylı dökümü

URL parametresiyle yıl seçebilirsiniz:
```
/yonetim/rapor?format=pdf&year=2024
/yonetim/rapor?format=excel&year=2025
```

---

## 5. Yerel Geliştirme (Docker olmadan)

```bash
# Sanal ortam
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Bağımlılıklar
pip install -r requirements.txt

# PostgreSQL çalışıyor olmalı, .env'de DB_HOST=localhost yapın
# Veya sadece DB'yi Docker'la çalıştırın:
docker compose up -d db

# Uygulamayı başlatın
uvicorn app.main:app --reload --port 8000
```

---

## 6. Veritabanı Tabloları

| Tablo | Açıklama |
|---|---|
| users | Hocalar ve adminler |
| projects | BAP projeleri |
| project_researchers | Proje-araştırmacı ilişkisi |
| outputs | Çıktılar (yayın, bildiri...) |
| attachments | Yüklenen ek dosyalar |

---

## 7. Güvenlik Kontrol Listesi (üretime almadan önce)

- [ ] .env'deki SECRET_KEY değiştirildi (en az 32 karakter rastgele string)
- [ ] DB_PASSWORD güçlü bir şifreyle değiştirildi
- [ ] Admin hesabı şifresi değiştirildi
- [ ] Sunucu 443 (HTTPS) üzerinden erişilebilir (nginx reverse proxy)
- [ ] LDAP bağlantısı test edildi
- [ ] Uploads klasörü için yedekleme planı yapıldı
