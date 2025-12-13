package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	exporterPort      = getEnvAsInt("EXPORTER_PORT", 17500)
	fetchInterval     = getEnvAsInt("FETCH_INTERVAL", 3600)
	cookieString      = os.Getenv("COOKIE_STRING")
	url               = os.Getenv("PROFILE_URL")
	userAgent         = os.Getenv("USER_AGENT")
	dlElementSelector = os.Getenv("DL_ELEMENT_SELECTOR")
	ulElementSelector = os.Getenv("UL_ELEMENT_SELECTOR")
	telegramBotToken  = os.Getenv("TELEGRAM_BOT_TOKEN")
	telegramChatID    = getEnvAsInt("TELEGRAM_CHAT_ID", 294967926)

	uploadMetric   = prometheus.NewGauge(prometheus.GaugeOpts{Name: "upload_value_bytes", Help: "Value extracted from the webpage in bytes"})
	downloadMetric = prometheus.NewGauge(prometheus.GaugeOpts{Name: "download_value_bytes", Help: "Value extracted from the webpage in bytes"})

	// Use lowercase keys for easier, case-insensitive lookup
	units = map[string]float64{
		"tib": 1 << 40, // TiB (Tebibytes)
		"tb":  1e12,    // TB (Terabytes)
		"gib": 1 << 30, // GiB
		"gb":  1e9,     // GB
		"mib": 1 << 20, // MiB
		"mb":  1e6,     // MB
		"kib": 1 << 10, // KiB
		"kb":  1e3,     // KB
	}
)

func init() {
	// Exit if required environment variables are not set
	if cookieString == "" || url == "" || userAgent == "" || dlElementSelector == "" || ulElementSelector == "" {
		log.Fatal("Required environment variables are not set")
		os.Exit(1)
	}
	prometheus.MustRegister(uploadMetric)
	prometheus.MustRegister(downloadMetric)
}

func getEnvAsInt(key string, defaultValue int) int {
	if value, exists := os.LookupEnv(key); exists {
		if intValue, err := strconv.Atoi(value); err == nil {
			return intValue
		}
	}
	return defaultValue
}

func ConvertHumanReadableSizeToBytes(input string) (float64, error) {
	// Remove text in parentheses
	input = regexp.MustCompile(`\([^)]*\)`).ReplaceAllString(input, "")
	// Normalize whitespace
	input = strings.TrimSpace(input)

	// Regex to find the first occurrence of a number followed by a unit.
	// Supports formats like:
	//   "435.96 GiB", "435.96GiB", "Uploaded: 435.96 GiB", "downloaded 304.22GB"
	re := regexp.MustCompile(`(?i)(\d+(?:\.\d+)?)\s*([kmgt]i?b)`)
	matches := re.FindStringSubmatch(input)
	if len(matches) < 3 {
		return 0, fmt.Errorf("invalid input format: %s", input)
	}

	valueStr := matches[1]
	unit := strings.ToLower(matches[2]) // e.g. "gib" or "gb"

	// Lookup multiplier using lowercase unit
	multiplier, ok := units[unit]
	if !ok {
		return 0, fmt.Errorf("unrecognized unit: %s", unit)
	}

	// Parse the numeric part
	value, err := strconv.ParseFloat(valueStr, 64)
	if err != nil {
		return 0, err
	}

	// Calculate the number of bytes
	bytes := value * multiplier
	return bytes, nil
}

func sendTelegramMessage(message string) {
	url := fmt.Sprintf("https://api.telegram.org/bot%s/sendMessage", telegramBotToken)

	payload := map[string]interface{}{
		"chat_id": telegramChatID,
		"text":    message,
	}
	payloadBytes, _ := json.Marshal(payload)

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(payloadBytes))
	if err != nil {
		log.Printf("Error creating Telegram request: %v", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil || resp.StatusCode != http.StatusOK {
		log.Printf("Failed to send message to Telegram: %v", err)
	}
}

func fetchValue() {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		log.Printf("Error creating request: %v", err)
		return
	}
	req.Header.Set("Cookie", cookieString)
	req.Header.Set("User-Agent", userAgent)

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("Error fetching webpage: %v", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		log.Printf("Failed to fetch webpage: %d", resp.StatusCode)
		return
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		log.Printf("Error parsing HTML: %v", err)
		return
	}

	uploadText := strings.TrimSpace(doc.Find(ulElementSelector).Text())
	downloadText := strings.TrimSpace(doc.Find(dlElementSelector).Text())
	// If there are no space between value and unit, add a space (e.g. "435.96GiB" -> "435.96 GiB")
	uploadText = regexp.MustCompile(`(\d)([A-Za-z])`).ReplaceAllString(uploadText, "$1 $2")
	downloadText = regexp.MustCompile(`(\d)([A-Za-z])`).ReplaceAllString(downloadText, "$1 $2")

	log.Printf("Upload: '%s'\n", uploadText)
	log.Printf("Download: '%s'\n", downloadText)

	if uploadText != "" {
		uploadBytes, err := ConvertHumanReadableSizeToBytes(uploadText)
		if err != nil {
			log.Printf("Invalid format for upload: %s", uploadText)
		} else {
			uploadMetric.Set(uploadBytes)
		}
	} else {
		log.Println("Upload element not found")
	}

	if downloadText != "" {
		downloadBytes, err := ConvertHumanReadableSizeToBytes(downloadText)
		if err != nil {
			log.Printf("Invalid format for download: %s", downloadText)
		} else {
			downloadMetric.Set(downloadBytes)
		}
	} else {
		log.Println("Download element not found")
	}
}

func main() {
	http.Handle("/metrics", promhttp.Handler())
	go func() {
		log.Fatal(http.ListenAndServe(fmt.Sprintf(":%d", exporterPort), nil))
	}()

	log.Println("Starting exporter...")
	log.Printf("Fetching URL: %s", url)

	for {
		fetchValue()
		time.Sleep(time.Duration(fetchInterval) * time.Second)
	}
}
