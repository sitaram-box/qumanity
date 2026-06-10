# ID Format

## Private ID (User ID)
*Based on birth location – never changes*

**Format:**
`[RandomPrefix]-[FirstInitial][LastInitial]-[GenderCode][AgeCode]-[ElementCode][SignCode]-[BirthLocationPath]`

## Public ID (Account ID)
*Based on present location – can change if user moves*

**Format:**
`[RandomPrefix]-[FirstInitial][LastInitial]-[GenderCode][AgeCode]-[ElementCode][SignCode]-[PresentLocationPath]`

## Components

| Part | Source | Example (Admin) |
| :--- | :--- | :--- |
| RandomPrefix | Random 3-4 alphanumeric characters | `X7K` |
| FirstInitial | First letter of first name | `R` |
| LastInitial | First letter of last name | `M` |
| GenderCode | `M` (Male), `F` (Female), `O` (Other) | `M` |
| AgeCode | `B`/`Y`/`V`/`S` | `Y` (Yuvak) |
| ElementCode | `F`/`E`/`A`/`W` | `F` (Fire) |
| SignCode | First letter of sun sign | `L` (Leo) |
| LocationPath | Zone.State.District.Tehsil.Village | `CS.DL.1.A.12` |

## Example (Admin Rohit Mudgal)

**Private ID:** `X7K-RM-GM-AY-FL-CS.DL.1.A.12`

**Public ID:** `X7K-RM-GM-AY-FL-CS.DL.5.4.1E`

## Admin Exception
Admin ID (`H_U_ADMIN`) is an exception – it does not follow the format and has no location ID.
