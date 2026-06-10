# Qoin Denominations

## Allowed Rupee Values

Only these rupee values can be stored in a single Qoin:

```
[2000, 500, 200, 100, 50, 20, 10, 5, 2, 1]
```

## Rules
- No Qoin can hold any other value (e.g., no ₹7 Qoin, no ₹300 Qoin)
- Weekly settlement (not real-time)
- Greedy algorithm for smallest number of Qoins

## Greedy Algorithm

```python
def min_qoins_for_amount(amount):
    qoins = []
    remaining = amount
    for denom in [2000, 500, 200, 100, 50, 20, 10, 5, 2, 1]:
        while remaining >= denom:
            qoins.append(denom)
            remaining -= denom
    return qoins
```

## Example
- ₹7 = ₹5 + ₹2 (2 Qoins)
- ₹300 = ₹200 + ₹100 (2 Qoins)
- ₹75 = ₹50 + ₹20 + ₹5 (3 Qoins)
