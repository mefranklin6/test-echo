// Very basic echo server for testing https://github.com/mefranklin6/Extron-Frontend-API
// This code is not intended for production use.
// 1. Server will toggle buttons not in the dontToggleButtons list
// 2. Server will update a label once per second with the current time
// 3. Server will update a slider when a slider event is received

package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"slices"
	"sync"
	"time"
)

// Begin User Variables //

// IP and Port of the machine running this code
const ServerAddr = "192.168.253.8:8080"

// IP and Port of the processors RPC server
const ProcessorAddr = "192.168.253.254:8081"

// Label that gets update once per second
const testLabel = "Lbl_Time"

// List of buttons that should not immidately toggle visual state
var dontToggleButtons = []string{"Btn_NoTog"}

// End User Variables //

const contentType = "application/json"

func main() {
	// Handle unsolicited data from the processor
	http.HandleFunc("/api/v1/button", replyButtonHandler)
	http.HandleFunc("/api/v1/slider", replySliderHandler)
	http.HandleFunc("/api/v1/test", replyTestHandler)

	// Send a test label periodically

	go startTicker()

	fmt.Println("Starting server at", ServerAddr)
	if err := http.ListenAndServe(ServerAddr, nil); err != nil {
		fmt.Println("Error starting server:", err)
	}
}

var conn net.Conn
var connErr error
var connMu sync.Mutex

// Getter function for the TCP connection
func getConn() (net.Conn, error) {
	connMu.Lock()
	defer connMu.Unlock()

	if conn == nil {
		fmt.Println("No existing connection.  Attempting to establish.")
		conn, connErr = net.Dial("tcp", ProcessorAddr)
		if connErr != nil {
			return nil, connErr
		} else {
			fmt.Println("Connected", conn.LocalAddr().String(), ">", conn.RemoteAddr().String())
		}
	}

	return conn, nil
}

type Response struct {
	Type     string `json:"type"`
	Object   string `json:"object"`
	Function string `json:"function"`
	Arg1     string `json:"arg1"`
	Arg2     string `json:"arg2"`
	Arg3     string `json:"arg3"`
}

type Rx struct {
	Name   string `json:"name"`
	Action string `json:"action"`
	Value  string `json:"value,omitempty"`
}

func startTicker() {
	// Non xi processors start to bug out at 10ms or lower
	ticker := time.NewTicker(20 * time.Millisecond)
	defer ticker.Stop()

	for range ticker.C {
		sendTestSetLabel()
	}
}

func replyTestHandler(w http.ResponseWriter, r *http.Request) {
	w.Write([]byte("OK"))
}

func btnVisStateToggle(rx Rx) ([]byte, error) {
	if slices.Contains(dontToggleButtons, rx.Name) {
		return nil, nil
	}

	state := "0"
	if rx.Value == "0" {
		state = "1"
	}

	response := Response{
		Type:     "Button",
		Object:   rx.Name,
		Function: "SetState",
		Arg1:     state,
	}
	fmt.Print(response)

	return json.Marshal(response)
}

func replyButtonHandler(w http.ResponseWriter, r *http.Request) {
	var rx Rx
	if err := json.NewDecoder(r.Body).Decode(&rx); err != nil {
		http.Error(w, "Invalid JSON data", http.StatusBadRequest)
		return
	}
	fmt.Print(rx)

	reply, err := btnVisStateToggle(rx)

	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", contentType)
	w.Write(reply)
}

func replySliderHandler(w http.ResponseWriter, r *http.Request) {
	var rx Rx
	if err := json.NewDecoder(r.Body).Decode(&rx); err != nil {
		http.Error(w, "Invalid JSON data", http.StatusBadRequest)
		return
	}

	fmt.Print(rx)
	name := rx.Name
	value := rx.Value

	response := Response{
		Type:     "Slider",
		Object:   name,
		Function: "SetFill",
		Arg1:     value,
	}

	fmt.Print(response)

	reply, err := json.Marshal(response)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", contentType)
	w.Write(reply)
}

func sendTestSetLabel() {
	response := Response{
		Type:     "Label",
		Object:   testLabel,
		Function: "SetText",
		Arg1:     time.Now().Format("15:04:05.00"),
	}

	data_to_send, err := json.Marshal(response)
	if err != nil {
		fmt.Println("Error creating response:", err)
		return
	}

	sendToProcessor(data_to_send)
}

func sendToProcessor(data_to_send []byte) {
	conn, err := getConn()
	if err != nil {
		fmt.Println("Error connecting to client:", err)
		return
	}

	// Create an HTTP request
	req, err := http.NewRequest("POST", "/", bytes.NewBuffer(data_to_send))
	if err != nil {
		fmt.Println("Error creating HTTP request:", err)
		return
	}
	req.Header.Set("Content-Type", contentType)

	// Write the HTTP request to the connection
	err = req.Write(conn)
	if err != nil {
		fmt.Println("Error sending HTTP request:", err)
		closeConn() // Close and set conn to nil
		return
	}
}

func closeConn() {
	connMu.Lock()
	defer connMu.Unlock()
	if conn != nil {
		conn.Close()
		conn = nil
	}
}
