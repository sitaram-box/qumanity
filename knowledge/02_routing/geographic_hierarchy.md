# Geographic Hierarchy (Nested Containers)

## Levels

```
Level 0: Planet (Earth)
Level 1: Continent (Asia, Africa, Europe, etc.)
Level 2: Country (India, USA, etc.)
Level 3: Zone (CS, NS, WS, SS, ES – for India only)
Level 4: State (Delhi, UP, Tamil Nadu, etc.)
Level 5: District (North West Delhi, etc.)
Level 6: Tehsil / Node (Bawana, etc.)
Level 7: Village (Rohini Sector-24, etc.)
Level 8: Citizen (Individual user)
```

## Location ID Format Example

`0.राम|IND/CS/DL.5.4.1E`

| Part | Meaning |
| :--- | :--- |
| `0.राम|` | Root prefix (Earth) |
| `IND` | India (Country) |
| `CS` | Central State (Zone) |
| `DL` | Delhi (State) |
| `5` | North West Delhi (District) |
| `4` | Bawana (Tehsil) |
| `1E` | Rohini Sector-24 (Village) |

## Zones in India

| Code | Zone Name |
| :--- | :--- |
| `CS` | Central State (UT & North-East) |
| `NS` | North India State |
| `WS` | West India State |
| `SS` | South India State |
| `ES` | East India State |
