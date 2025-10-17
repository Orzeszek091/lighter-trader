# lighter-trader

Минимальный пример на Python для открытия позиций на Lighter (market/limit) через официальный SDK.

## Установка

```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt

# подготовь .env на основе примера
cp .env.example .env  # или copy .env.example .env на Windows
# затем впиши свои значения
```

## Запуск

Market (long 0.05 ETH по market_id=0):
```bash
python src/open_position.py --side buy --qty 0.05 --market-id 0
```

Market через символ:
```bash
python src/open_position.py --side buy --qty 0.05 --symbol ETH
```

Limit post-only (sell 0.03 по 4123.5):
```bash
python src/open_position.py --type limit --side sell --qty 0.03 --price 4123.5 --symbol ETH --price-exp-hint 6
```
