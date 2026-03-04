# Katkıda Bulunma Rehberi

OpenWorld'e katkıda bulunduğunuz için teşekkürler!

## Geliştirme Ortamı

### Gereksinimler

- Python 3.11+
- Node.js 20+
- Git

### Kurulum

```bash
# Repo'yu klonla
git clone https://github.com/AhmetDemiroglu/OpenWorld.git
cd OpenWorld

# Backend kurulum
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt

# Frontend kurulum
cd frontend
npm install
```

## Kod Standartları

### Python

- PEP 8 uyumlu
- Type hints kullanın
- Docstring ekleyin
- Test yazın

### JavaScript/TypeScript

- ESLint kurallarına uyun
- Prettier formatı kullanın
- TypeScript tercih edin

## Katkı Adımları

1. **Fork** yapın
2. **Branch** oluşturun: `git checkout -b feature/yeni-ozellik`
3. **Değişikliklerinizi** yapın
4. **Test** edin: `pytest` / `npm test`
5. **Commit** yapın
6. **Push** edin
7. **Pull Request** açın

## Commit Mesajları

- feat: Yeni özellik
- fix: Hata düzeltmesi
- docs: Dokümantasyon
- style: Kod formatı
- refactor: Refactoring
- test: Test ekleme
- chore: Bakım işleri

## Pull Request

- Açıklayıcı başlık ve açıklama
- İlgili issue'ları bağlayın
- Testleri çalıştırın
- Kod review'a hazır olun

## Sorular?

GitHub Discussions veya Issues kullanabilirsiniz.
