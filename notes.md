# Hardware Specifications and Behaviors

## Board:
- Raspberry Pi 3B
- OS: Raspberry Pi OS Trixie

## Keypad:
*Rows and columns are connected directly to pins with no diodes. Internal pull-ups are used. Strokes are detected on falling edge (key press) and do not repeat if the key is held.*

Rows:
- 26, 21, 20, 16
		
Columns:
- 12, 24, 23, 18
		
Layout:
	F1, 1, 2, 3
	F2, 4, 5, 6
	F3, 7, 8, 9
	14, CLR, 0, ENT
		
	Multi-Tap Character Assignment:
		Maxiumum delay between key presses to cycle character: 500ms
		After this delay, the cursor moves on to the next character.
		0: 0
		1: 1, Q, Z
		2: 2, A, B, C
		3: 3, D, E, F
		4: 4, G, H, I
		5: 5, J, K, L
		6: 6, M, N, O
		7: 7, P, R, S
		8: 8, T, U, V
		9: 9, W, X, Y
	
	Function Assignment:
		F1: Up "up"
		F2: Down "down"
		F3: Backspace "bsp"
		F4: Escape "esc"
		CLR: Clear "clr"
		ENT: Enter "ent"

Power:		
	Press green button 3x to shut down, 1x to wake.
	Shutdown: 17
	Wake: 3

Switches:
	Switches connect to GND, so should have internal pull-ups.
	Yellow (Withdraw): 19 "withdraw"
	Blue (Deposit): 13 "deposit"
	White (Print): 6 "print"
	Red (Read/Scan): 5 "read"

Printer:
	Baud rate: 19200
	Firmware version: 2.16
	TX: 14
	RX: Not connected

Screen:
	Driver: ILI9341
	Width, Height: 320, 240
	SCLK: 11
	MOSI: 10
	MISO: Not connected
	CS: CE0
	DC: 25
	RST: 24

NFC:
	No interrupt pin connected
	SDA: 2
	SCL: 3

Camera:
	Logitech USB webcam
	Width, Height: 1920, 1080

