# Troubleshooting Guide

## Common Errors

### Database error: `unable to open database file`

**Solution:**
```bash
chmod 664 indiaq.db
chmod 775 .
```

### Database error: `no such table: wallets`

**Solution:**
```bash
python3 init_db.py
```

### Language not changing

**Solution:**
- Clear browser cache
- Check `session['preferred_language']` in browser dev tools
- Ensure all UI text uses `{{ 'key'|tr }}` filter

### Marquee not showing poems

**Solution:**
- Check `static/poems.json` exists
- Check browser console for errors
- Verify `fetch('/static/poems.json')` returns 200

### Admin cannot log in

**Solution:**
```bash
python3 recreate_admin.py
```

### Port 5000 already in use (macOS AirPlay)

**Solution:**
```bash
python3 app.py --port 5001
# Or disable AirPlay Receiver in System Settings
```

### Module not found

**Solution:**
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Git: `fatal: not in a git directory`

**Solution:**
```bash
git init
git remote add origin https://github.com/your-username/quantum-box.git
```

### Docker: `bind: address already in use`

**Solution:**
```bash
docker ps
docker stop <container_id>
```
