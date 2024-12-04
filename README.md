# Test-Echo

Rough proof of concept / dev enviroment for <https://github.com/mefranklin6/Extron-Frontend-API>

## Includes

- Simple GUI File, made for TLP Pro 725
- Instantiated GUI Objects
- Go Backend Server

## Actions

- Server will toggle buttons not in the `dontToggleButtons` list (in the Go server) when pressed by a user
- Server will update a slider fill when a slider event is received
- Server will update a label once per second with the current time

## Deployment

1. Deploy everything within `test-echo_processor_files` with CSDU as normal. (Change your IP's and hardware if needed, format the GUI file for your touch panel if not using TLP Pro 725T).  
Make sure to write the config.json to your processor as detailed in the deployment steps here <https://github.com/mefranklin6/Extron-Frontend-API>

2. Install Go if needed. <https://go.dev/doc/install>

3. Change the IP addresses of the server and processor if needed at the top of `server.go`

4. Compile and run the server.  In a terminal or in VSCode Terminal, navigate to the folder that has `server.go` in it and `go run server.go`

Exmple (should be the same on Powershell in Windows as it is on Bash in Linux):

```bash
cd /path/to/test-echo
go run server.go
```

## FAQ

Q: Does the backend server need to be written in Go?

A: Not at all.  You can use whatever you want.  See the benefits at the readme here <https://github.com/mefranklin6/Extron-Frontend-API>.
