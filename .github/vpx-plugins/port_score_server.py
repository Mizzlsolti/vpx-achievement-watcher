"""Port superhac's score-server plugin to the VPX 10.8.1 plugin API.

score-server was written in January 2026 against an older VPX plugin API.
VPX 10.8.1 changed a few things; this script adapts the original source in
place (the upstream repository stays untouched):

* Controller game events (CTLPI_EVT_ON_GAME_START/END with a CtlOnGameStartMsg
  carrying the ROM name) no longer exist.  VPX's own player events are used
  instead and the ROM name is read from the PinMAME controller ("GameName")
  as soon as the table script has created it (polled on OnPrepareFrame).
* The PinMAME script class is registered as "PinMAME_Controller".
* MsgPluginAPI::UnsubscribeMsg takes the userData argument.
* Scriptable class macros (PSC_CLASS_START/PSC_FUNCTIONn/PSC_CLASS_END) and
  SubmitTypeLibrary(endpointId) have new signatures.

Usage: python port_score_server.py <path/to/score-server.cpp>
The script fails loudly if an expected anchor is missing, so a changed
upstream source is noticed in CI instead of producing a broken plugin.
"""

import re
import sys
from pathlib import Path


def sub_once(src: str, old: str, new: str, what: str) -> str:
    if old not in src:
        sys.exit(f"[port] anchor not found: {what}")
    return src.replace(old, new, 1)


def main(path: str) -> None:
    p = Path(path)
    s = p.read_text(encoding="utf-8")
    if "VPX 10.8.1 port" in s:
        print("[port] already ported")
        return

    # 1) Controller helpers (class lookup + GameName), placed before first use.
    helpers = r'''
// ---- VPX 10.8.1 port (Achievement Watcher) ---------------------------------
// The PinMAME scriptable class is registered as "PinMAME_Controller" in 10.8.1.
static ScriptClassDef* getControllerClassDef() {
    if (!scriptApi) return nullptr;
    ScriptClassDef* def = scriptApi->GetClassDef("PinMAME_Controller");
    if (!def) def = scriptApi->GetClassDef("Controller");
    return def;
}

// Read a string property (getter without arguments) from the PinMAME controller.
static std::string getControllerString(const char* prop) {
    ScriptClassDef* def = getControllerClassDef();
    if (!def || !pinmameController) return std::string();
    for (unsigned int i = 0; i < def->nMembers; i++) {
        if (std::string(def->members[i].name.name) == prop && def->members[i].nArgs == 0) {
            ScriptVariant result = {};
            def->members[i].Call(pinmameController, (int)i, nullptr, &result);
            std::string value = result.vString.string ? std::string(result.vString.string) : std::string();
            if (result.vString.Release) result.vString.Release(&result.vString);
            return value;
        }
    }
    return std::string();
}

// Running ROM: "ROMName" is the resolved driver (aliases like afm_113Serum
// become afm_113b, matching the NVRAM maps); "GameName" is the requested name.
static std::string getControllerGameName() {
    std::string rom = getControllerString("ROMName");
    if (rom.empty()) rom = getControllerString("GameName");
    return rom;
}
// ----------------------------------------------------------------------------

'''
    s = sub_once(s, "// Get NVRAM data directly from PinMAME Controller via Scriptable API\n",
                 helpers + "// Get NVRAM data directly from PinMAME Controller via Scriptable API\n",
                 "getNVRAMFromController header")
    s = sub_once(s, 'ScriptClassDef* controllerClass = scriptApi->GetClassDef("Controller");',
                 "ScriptClassDef* controllerClass = getControllerClassDef();", "GetClassDef(Controller)")

    # 2) Game start: VPX player start -> wait for the PinMAME controller.
    old_start = ("void onGameStart(const unsigned int eventId, void* userData, void* eventData) {\n"
                 "    // Game starting - get the ROM name\n"
                 "    CtlOnGameStartMsg* msg = static_cast<CtlOnGameStartMsg*>(eventData);\n"
                 "    if (msg && msg->gameId) {\n"
                 "        currentRomName = msg->gameId;\n")
    new_start = ("static bool romPending = false;\n"
                 "static unsigned int romPollCounter = 0;\n"
                 "void startRomGame(const char* gameId);\n\n"
                 "void onGameStart(const unsigned int eventId, void* userData, void* eventData) {\n"
                 "    // VPX 10.8.1: the player starts before the table script creates the\n"
                 "    // PinMAME controller, so the ROM name is resolved in onPrepareFrame.\n"
                 "    romPending = true;\n"
                 "    romPollCounter = 0;\n"
                 "    pinmameController = nullptr;\n"
                 "}\n\n"
                 "void startRomGame(const char* gameId) {\n"
                 "    if (gameId && *gameId) {\n"
                 "        currentRomName = gameId;\n")
    s = sub_once(s, old_start, new_start, "onGameStart")

    old_end = "void onGameEnd(const unsigned int eventId, void* userData, void* eventData) {\n"
    s = sub_once(s, old_end, old_end + "    romPending = false;\n"
                 "    if (currentRomName.empty()) return; // no PinMAME game was running\n",
                 "onGameEnd")

    old_frame = ("void onPrepareFrame(const unsigned int eventId, void* userData, void* eventData) {\n")
    new_frame = old_frame + (
        "    if (romPending && (romPollCounter++ % 30) == 0) {\n"
        "        void* ctrl = nullptr;\n"
        "        msgApi->BroadcastMsg(endpointId, getControllerId, &ctrl);\n"
        "        if (ctrl) {\n"
        "            pinmameController = ctrl;\n"
        "            std::string gameName = getControllerGameName();\n"
        "            if (!gameName.empty()) {\n"
        "                romPending = false;\n"
        "                startRomGame(gameName.c_str());\n"
        "            }\n"
        "        }\n"
        "    }\n")
    s = sub_once(s, old_frame, new_frame, "onPrepareFrame")

    # 3) Subscriptions: VPX player events instead of controller events.
    s = s.replace("msgApi->GetMsgID(CTLPI_NAMESPACE, CTLPI_EVT_ON_GAME_START)",
                  "msgApi->GetMsgID(VPXPI_NAMESPACE, VPXPI_EVT_ON_GAME_START)")
    s = s.replace("msgApi->GetMsgID(CTLPI_NAMESPACE, CTLPI_EVT_ON_GAME_END)",
                  "msgApi->GetMsgID(VPXPI_NAMESPACE, VPXPI_EVT_ON_GAME_END)")
    if "CTLPI_EVT_ON_GAME" in s:
        sys.exit("[port] unexpected CTLPI_EVT_ON_GAME usage left")

    # 4) UnsubscribeMsg(msgId, callback, userData)
    s, n = re.subn(r"msgApi->UnsubscribeMsg\((\w+),\s*(\w+)\);", r"msgApi->UnsubscribeMsg(\1, \2, nullptr);", s)
    if n == 0:
        sys.exit("[port] no UnsubscribeMsg calls found")

    # 5) Scriptable class macros
    def fix_func(m):
        n_args, rest = m.group(1), m.group(2)
        parts = [x.strip() for x in rest.split(",")]
        if parts and parts[0] == "ScoreServerClass":
            parts = parts[1:]
        return f"PSC_FUNCTION{n_args}({', '.join(parts)})"
    s = re.sub(r"PSC_FUNCTION(\d+)\(([^)]*)\)", fix_func, s)
    s = sub_once(s, "PSC_CLASS_START(ScoreServerClass)\n", "PSC_CLASS_START(ScoreServerClass, ScoreServerClass)\n",
                 "PSC_CLASS_START")
    s = sub_once(s, "PSC_CLASS_END(ScoreServerClass)", "PSC_CLASS_END()", "PSC_CLASS_END")
    s = sub_once(s, "RegisterScoreServerClassSCD(", "RegisterScoreServerClass(", "RegisterScoreServerClassSCD")
    s = sub_once(s, "scriptApi->SubmitTypeLibrary();", "scriptApi->SubmitTypeLibrary(endpointId);", "SubmitTypeLibrary")

    # 6) Achievement Watcher extension.
    #    * round_start: a new pinball game begins (ball goes from 0 to 1+).
    #      score-server only re-arms its game_end trigger here, it sends no
    #      message, so the Watcher would not know where a round begins.
    #    * nvram_snapshot: the live NVRAM, sent immediately on every player /
    #      ball change and otherwise whenever it changed, at most once per
    #      second. The Watcher decodes it with its NVRAM maps (live
    #      achievements, per-round and per-player statistics).
    snap = r'''
    // ---- Achievement Watcher: round start + NVRAM snapshots ----
    {
        static int awPrevBall = -1;
        static int awSnapPlayers = -1, awSnapPlayer = -1, awSnapBall = -1;
        static std::string awSnapRom;
        static std::vector<uint8_t> awSnapData;
        static std::chrono::steady_clock::time_point awSnapTime;

        if (awSnapRom != currentRomName) {
            awPrevBall = -1;
        }
        if (awPrevBall == 0 && currentBall > 0) {
            std::stringstream roundMsg;
            roundMsg << "{\"type\":\"round_start\","
                     << "\"timestamp\":\"" << getTimestamp() << "\","
                     << "\"rom\":\"" << currentRomName << "\""
                     << addMachineIdField() << ","
                     << "\"players\":" << playerCount << ","
                     << "\"current_player\":" << currentPlayer << ","
                     << "\"current_ball\":" << currentBall << "}";
            broadcastWebSocket(roundMsg.str());
        }
        awPrevBall = currentBall;

        const auto awNow = std::chrono::steady_clock::now();
        const bool awStateChanged = (playerCount != awSnapPlayers || currentPlayer != awSnapPlayer ||
                                     currentBall != awSnapBall || awSnapRom != currentRomName);
        const bool awDataChanged = (liveNvram != awSnapData);
        const bool awThrottleOk = (awNow - awSnapTime) >= std::chrono::milliseconds(1000);
        if (awStateChanged || (awDataChanged && awThrottleOk)) {
            awSnapPlayers = playerCount; awSnapPlayer = currentPlayer;
            awSnapBall = currentBall; awSnapRom = currentRomName;
            awSnapData = liveNvram;
            awSnapTime = awNow;
            std::stringstream snapMsg;
            snapMsg << "{\"type\":\"nvram_snapshot\","
                    << "\"timestamp\":\"" << getTimestamp() << "\","
                    << "\"rom\":\"" << currentRomName << "\""
                    << addMachineIdField() << ","
                    << "\"players\":" << playerCount << ","
                    << "\"current_player\":" << currentPlayer << ","
                    << "\"current_ball\":" << currentBall << ","
                    << "\"base\":" << nvramBaseAddress << ","
                    << "\"size\":" << liveNvram.size() << ","
                    << "\"data\":\"" << base64_encode(liveNvram.data(), liveNvram.size()) << "\"}";
            broadcastWebSocket(snapMsg.str());
        }
    }
'''
    anchor = "    int currentBall = decodeValue(liveNvram, currentBallObj);\n"
    fn = "void checkAndBroadcastCurrentScores() {"
    if fn not in s:
        sys.exit("[port] anchor not found: checkAndBroadcastCurrentScores")
    pos = s.index(anchor, s.index(fn))  # hook the per-frame function, not the logger
    s = s[:pos + len(anchor)] + snap + s[pos + len(anchor):]

    s = "// VPX 10.8.1 port applied by vpx-achievement-watcher/.github/vpx-plugins/port_score_server.py\n" + s
    p.write_text(s, encoding="utf-8")
    print("[port] score-server ported to the VPX 10.8.1 plugin API")


if __name__ == "__main__":
    main(sys.argv[1])
