; Move to loading position and wait
; Absolute positioning
G90
; Move Z to safe height
G53 G0 Z-4

; Save safe position
G28.1

; Move to front-center and pause the program
G53 G0 X-600Y-1200
; Pause for tool change
M0

; Move to touch plate and probe
; Move to touch plate
G53 G0 X-1.588Y-1222.85

; Cancel tool length offset
G49
; Z-Probe
G91
; Probe fast
G38.2 Z-200 F450
; Retract 4mm
G0 Z4
; Probe slowly
G38.2 Z-10 F50
; Dwell for one second
G4 P1
; Set tool length offset
G43.1 Z[posz]
; Retract from the touch plate
G0 Z4

; Return to the original position
G90
G53 G0 Z-4
G28