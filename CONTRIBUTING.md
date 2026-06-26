# Как работать вдвоём над credits

Репозиторий: [lesnycode/credits](https://github.com/lesnycode/credits) → [credits.podlesnytwins.com](https://credits.podlesnytwins.com)

## Перед каждым push

```bash
git pull --rebase origin main
```

Если меняли `index.html`:

```bash
python3 build_who_mixed.py
git add -A
```

```bash
git commit -m "описание"   # если есть изменения
git push origin main
```

## Кто что трогает

| Файл | Кто |
|------|-----|
| `index.html` | дизайн, плитки, CSS, JS |
| `build_credits.py`, `build_who_mixed.py` | скрипты — **после** коммита с `index.html` |
| `track/` | **не вручную** — только через `build_who_mixed.py` |

## Ветки (если часто конфликтуете)

```bash
git checkout -b anton/название   # или pavel/...
# работа → push → merge в main
```

## Конфликт в index.html

1. Открыть файл, убрать маркеры `<<<<<<<` / `=======` / `>>>>>>>`
2. `git add index.html && git rebase --continue`
3. `python3 build_who_mixed.py && git add track/ sitemap.xml`
4. `git push origin main`

## Деплой

Push в `main` → GitHub Actions деплоит на Pages автоматически (~1–2 мин).