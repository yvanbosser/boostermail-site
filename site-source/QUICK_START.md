# BoosterMail Build System — Quick Start Guide

## ⚡ Most Common Commands

### Add a New Article
```bash
cd C:\EasyMail

# 1. Edit site-source/data/articles.json
#    Add new article object with:
#    - id, slug, title_fr, description_fr, keywords_fr, date, readTime, emoji, category_fr

# 2. Build everything (translate + generate)
$env:PYTHONIOENCODING='utf-8'
python site-source/build.py all
```

### Regenerate All Files (After Editing)
```bash
$env:PYTHONIOENCODING='utf-8'
python site-source/build.py all
```

### Just Translate (No Generation)
```bash
$env:PYTHONIOENCODING='utf-8'
python site-source/build.py translate
```

### Just Generate (No Translation)
```bash
$env:PYTHONIOENCODING='utf-8'
python site-source/build.py generate
```

---

## 📋 File Locations Reference

| File | Purpose | Edit? |
|------|---------|-------|
| `C:\EasyMail\site-source\data\articles.json` | Article content source | ✅ YES |
| `C:\EasyMail\site-source\data\site-content.json` | Nav/footer UI text | ⚠️ RARELY |
| `C:\EasyMail\site-source\build.py` | Build orchestration | ❌ NO |
| `C:\EasyMail\site web\` | Generated HTML (upload to Netlify) | ❌ NO |

---

## ✅ Verification Checklist

After running `build.py all`, verify:

- [ ] No error messages (check for ❌ in output)
- [ ] Message shows "✅ Généré XX fichiers article HTML"
- [ ] Message shows "✅ Génération HTML terminée"
- [ ] `C:\EasyMail\site web\` contains new HTML files
- [ ] Files are dated today (check modification time)

---

## 🔧 Troubleshooting

### "UnicodeEncodeError" when running python
**Solution:** Always use PowerShell and set encoding:
```powershell
$env:PYTHONIOENCODING='utf-8'
python site-source/build.py all
```

### "Validation échouée: Article... readTime doit être un entier"
**Solution:** In articles.json, remove quotes around numbers:
```json
// ❌ Wrong
"readTime": "8"

// ✅ Correct
"readTime": 8
```

### Articles not appearing in other languages
**Solution:** Run `build.py all` to regenerate everything with translations.

### Emojis missing in non-French versions
**Solution:** This should not happen with the new system. If it does, regenerate:
```powershell
$env:PYTHONIOENCODING='utf-8'
python site-source/build.py generate
```

---

## 📊 System Health

The system automatically:
- ✅ Retries API calls 3 times (handles temporary failures)
- ✅ Validates all data before processing
- ✅ Shows progress bars during translation
- ✅ Generates all 4 language versions
- ✅ Maintains emoji consistency
- ✅ Prevents file corruption

No manual intervention needed unless errors appear.

---

## 🚀 Deployment

After verifying the files:

```bash
# 1. Go to Netlify (https://app.netlify.com)
# 2. Drag & drop C:\EasyMail\site web\ folder
# 3. Wait for deployment
# 4. Test on boostermail.ai
```

---

**Need help?** See `README.md` for detailed documentation.
