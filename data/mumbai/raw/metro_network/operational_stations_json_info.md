Mumbai Metro JSON — Schema & Handling Context
Dataset Structure

The JSON represents Mumbai Metro operational station data:

dataset
├── name: string
├── as_of: string
├── coordinate_policy: string
└── lines: array<Line>
    └── Line
        ├── line: string
        ├── color: string
        ├── route: string
        ├── station_count: integer
        └── stations: array<Station>
            └── Station
                ├── number: integer
                ├── station_name: string
                ├── latitude: number [optional]
                ├── longitude: number [optional]
                ├── plus_code: string [optional]
                └── interchange: array<string>

Field Semantics
dataset
name: Dataset name.
as_of: Reference/effective date of the dataset.
coordinate_policy: Rules for handling geographic coordinates.
lines: List of metro lines.
line
line: Line identifier, e.g. Line 1, Line 2A.
color: Line color.
route: Directional route in Origin → Destination format.
station_count: Declared number of stations.
stations: Ordered list of stations on the line.
station
number: Sequential station number within the line.
station_name: Station name.
latitude, longitude: Explicit geographic coordinates; both are optional.
plus_code: Google Maps Plus Code; optional and retained exactly as provided.
interchange: List of connected metro lines, railways, airports, monorail, or other transport connections. [] means no interchange is specified.
Coordinate Rules
Use only coordinates explicitly supplied in the JSON or explicitly approved by the user.
Do not infer, calculate, geocode, approximate, or substitute missing coordinates.
If latitude/longitude are absent, preserve and use the supplied plus_code.
Do not convert Plus Codes into latitude/longitude unless explicitly instructed.
Treat Plus Codes as exact source values.
LLM Handling Rules
Preserve station ordering using number.
Treat station_count as the declared count; validate against stations.length if needed.
A station may have coordinates or a Plus Code.
Do not assume every station has the same coordinate representation.
interchange may contain operational connections as well as notes such as planned, future, or connection.
Do not interpret an interchange as operational solely because it appears in the array; inspect its text for qualifiers.
Station names should be treated as strings and preserved as provided.
Line names, colors, routes, and station data should not be inferred or normalized unless explicitly requested.
Example Station Variants

Coordinate-based:

{
  "number": 1,
  "station_name": "Versova",
  "latitude": 19.130306,
  "longitude": 72.821306,
  "interchange": []
}


Plus-Code-based:

{
  "number": 1,
  "station_name": "Mahashtranagar - Mandale",
  "plus_code": "2WXQ+V9 Mumbai, Maharashtra, India",
  "interchange": []
}


Interchange example:

{
  "station_name": "Marol Naka",
  "latitude": 19.108195,
  "longitude": 72.879536,
  "interchange": ["Line 1"]
}

Current Dataset Characteristics
Reference date: September 2026
Lines represented: 6
Line 1
Line 2A
Line 2B
Line 3
Line 7
Line 9
Total station records: 79
Geographic values can be either explicit latitude/longitude or a supplied plus_code.
The source coordinate policy takes precedence over assumptions or external geographic data.