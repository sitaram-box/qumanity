# Location ID Format

## Structure

`0.राम|[Country Code]/[Zone Code]/[State Code].[District Code].[Tehsil Code].[Village Code]`

## Example Breakdown

`0.राम|IND/CS/DL.5.4.1E`

| Segment | Value | Meaning |
| :--- | :--- | :--- |
| Root | `0.राम|` | Earth / Global |
| Country | `IND` | India |
| Zone | `CS` | Central State |
| State | `DL` | Delhi |
| District | `5` | North West Delhi |
| Tehsil | `4` | Bawana |
| Village | `1E` | Rohini Sector-24 |

## Parent-Child Relationship
- To get parent ID, remove the last segment
- Example parent of village: `0.राम|IND/CS/DL.5.4`
