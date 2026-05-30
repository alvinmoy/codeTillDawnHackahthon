// main.cc
// Sayam vitals producer.
//
// Wraps the Presage SmartSpectra C++ SDK and streams vitals to stdout as
// line-delimited JSON (one JSON object per line), so the Python Sayam
// orchestrator can read it from a subprocess pipe.
//
// stdout  -> ONLY machine-readable JSON envelopes, one per line:
//              {"type":"metrics","ts":<us>,"data":{...presage metrics...}}
//              {"type":"status","ts":<us>,"code":<int>,"hint":"..."}
//              {"type":"error","message":"..."}
// stderr  -> human-readable logs (safe to ignore / tee to a log file)
//
// Usage:
//   ./sayam_vitals --api_key=YOUR_KEY [--camera_device_index=0]
//   SMARTSPECTRA_API_KEY=YOUR_KEY ./sayam_vitals          # key via env
//   ./sayam_vitals --input_video_path=clip.mp4            # test from a file

#include <cstdlib>
#include <iostream>
#include <string>

#include <absl/flags/flag.h>
#include <absl/flags/parse.h>
#include <google/protobuf/util/json_util.h>

#include <smartspectra/smartspectra.h>
#include <smartspectra/smartspectra_config.h>
#include <smartspectra/smartspectra_types.h>

namespace spectra = presage::smartspectra;

ABSL_FLAG(std::string, api_key, "",
          "API key for the Presage Physiology service. "
          "Falls back to the SMARTSPECTRA_API_KEY environment variable.");
ABSL_FLAG(int, camera_device_index, 0, "Index of the camera device to use.");
ABSL_FLAG(int, capture_width_px, 1280, "Capture width in pixels.");
ABSL_FLAG(int, capture_height_px, 720, "Capture height in pixels.");
ABSL_FLAG(int, capture_fps, 30, "Capture frames per second.");
ABSL_FLAG(std::string, input_video_path, "",
          "Path to a video file to analyze instead of a live camera.");

namespace {

// Serialize a protobuf message to compact (single-line) JSON.
std::string ToCompactJson(const google::protobuf::Message& message) {
    std::string json;
    google::protobuf::util::JsonPrintOptions options;
    options.add_whitespace = false;  // keep it to a single line for stream parsing
    (void)google::protobuf::util::MessageToJsonString(message, &json, options);
    return json;
}

// Emit one JSON envelope line to stdout and flush so the Python reader sees it
// immediately rather than waiting on pipe buffering.
void EmitLine(const std::string& line) {
    std::cout << line << '\n' << std::flush;
}

}  // namespace

int main(int argc, char** argv) {
    absl::ParseCommandLine(argc, argv);

    std::string api_key = absl::GetFlag(FLAGS_api_key);
    if (api_key.empty()) {
        if (const char* env = std::getenv("SMARTSPECTRA_API_KEY")) {
            api_key = env;
        }
    }
    if (api_key.empty()) {
        std::cerr << "No API key provided. Pass --api_key=... or set "
                     "SMARTSPECTRA_API_KEY.\n";
        EmitLine(R"({"type":"error","message":"missing api key"})");
        return EXIT_FAILURE;
    }

    spectra::SmartSpectraConfig config;
    config.api_key = api_key;
    // DefaultSupportedMetrics() is breathing-only — cardio fields stay empty
    // unless we also request a cardio metric. Add the cardio bundle so we get
    // pulse rate, HRV, and the Baevsky stress index alongside breathing.
    config.requested_metrics = spectra::SmartSpectraConfig::DefaultSupportedMetrics();
    config.AddMetrics(spectra::SmartSpectraConfig::CardioMetrics());

    spectra::SmartSpectra smart_spectra(std::move(config));

    // Vitals arrive here. Wrap the SDK's metrics JSON in an envelope with the
    // timestamp so the Python side can correlate samples.
    smart_spectra.SetOnMetrics(
        [](const spectra::Metrics& metrics, int64_t ts) {
            EmitLine("{\"type\":\"metrics\",\"ts\":" + std::to_string(ts) +
                     ",\"data\":" + ToCompactJson(metrics) + "}");
        });

    // Face/lighting/validation feedback — useful for telling the user
    // "move into better light" before vitals can be computed.
    smart_spectra.SetOnValidationStatusChanged(
        [](const spectra::ValidationStatus& vs, int64_t ts) {
            std::string hint = vs.hint;
            // Escape any double-quotes in the hint for valid JSON.
            std::string escaped;
            for (char c : hint) {
                if (c == '"' || c == '\\') escaped += '\\';
                escaped += c;
            }
            EmitLine("{\"type\":\"status\",\"ts\":" + std::to_string(ts) +
                     ",\"code\":" + std::to_string(static_cast<int>(vs.code)) +
                     ",\"hint\":\"" + escaped + "\"}");
            std::cerr << "[status] code=" << static_cast<int>(vs.code)
                      << " hint=" << vs.hint << '\n';
        });

    smart_spectra.SetOnError([](const spectra::SmartSpectraError& error) {
        std::cerr << "[error] " << error.FullMessage() << '\n';
        EmitLine(R"({"type":"error","message":"see stderr"})");
    });

    // --- Video source: live camera, or a file when --input_video_path is set. ---
    const std::string video_path = absl::GetFlag(FLAGS_input_video_path);
    if (video_path.empty()) {
        const auto source_error =
            smart_spectra.UseCamera(absl::GetFlag(FLAGS_camera_device_index))
                .SetResolution(absl::GetFlag(FLAGS_capture_width_px),
                               absl::GetFlag(FLAGS_capture_height_px))
                .SetFps(absl::GetFlag(FLAGS_capture_fps))
                .Build();
        if (!source_error.ok()) {
            std::cerr << "UseCamera failed: "
                      << (source_error.message.empty() ? "no camera available"
                                                       : source_error.message)
                      << '\n';
            return EXIT_FAILURE;
        }
    } else {
        const auto source_error = smart_spectra.UseFile(video_path).Build();
        if (!source_error.ok()) {
            std::cerr << "UseFile failed: " << source_error.message << '\n';
            return EXIT_FAILURE;
        }
    }

    if (const auto err = smart_spectra.Start(); !err.ok()) {
        std::cerr << err.FullMessage() << '\n';
        return EXIT_FAILURE;
    }

    std::cerr << "[sayam_vitals] running (Ctrl+C to stop)\n";
    smart_spectra.WaitUntilComplete();  // blocks until EOF (file) or Stop() (camera)

    if (const auto err = smart_spectra.Stop(); !err.ok()) {
        std::cerr << "Stop failed: " << err.message << '\n';
    }
    std::cerr << "[sayam_vitals] done\n";
    return 0;
}
