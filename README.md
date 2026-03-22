
🏆 Achievement Progress & System: The tool recognizes game actions (e.g., ramps hit, multiballs activated, jackpots) and automatically unlocks achievements—either for the current game session or globally as long-term motivation.

📊 Highlights & Overlays: After a game (or at the touch of a button on the keyboard/controller), transparent info windows appear directly above the pinball machine. These show the best actions of the game and statistics. Supports portrait mode specifically for pinball cabinets.

⚔️ Challenge Modes like Pinball FX

Timed Challenge: Achieve the maximum score in 3 or 5 minutes.

Flip Challenge: How many points can you score with a limited number of pinball finger strokes? Select your difficulty level (e.g., Pro = Only 100 flips!).

Heat Challenge: When the barometer reaches 100%, it's over. The heat rises if you hold down the button or press it too quickly. But it cools down when you let go.

🔔 Feedback: Displays small pop-up notifications (toasts) directly after the  game when you achieve a success and offers optional voice output for challenge events.

💾 Statistics history: Records every round played, the duration of the game, and the points scored in the background. These can be conveniently evaluated in the user interface (GUI).

☁️ Leaderboards Compete with the community! The tool uploads your challenge scores and achievement progress (in %) to the cloud (if desired). 

(Tip: You can find your personal 4-digit player ID in the "System" tab. Make a note of it! If you ever install Watcher on a new PC, you can use it to restore your cloud progress.)

🛡️ Fair play & anti-cheat To keep the leaderboards fair, local saves and scores are protected by hash signatures (supporting signals that help detect casual tampering, but not final proof). Every cloud upload includes metadata (player ID, ROM, VPS table ID, watcher version, timestamp) that the server uses to validate submissions. The watcher blocks uploads when a required field is missing or when the ROM is not linked to a VPS table. Submissions may be `accepted`, `flagged` for review, or `rejected` — the server is always the authoritative anti-cheat layer. The client surfaces the result via the **Status Overlay** so you always know the state of your upload. For the full rules and watcher/server responsibility split, see [docs/cloud-anti-cheat.md](docs/cloud-anti-cheat.md). 

VPC Weekly Challenge view. Discords Weekly Challenge on Overlay (Only view)

The achievement watcher uses nvram-maps, vpc-data, vps and vpxtool for Visual Pinball

## WatcherInjector / Live Player Switching

When a table with a valid NVRAM map becomes active, the watcher automatically
writes **`AW_hook.ini`** into the watcher base directory (`BASE\AW_hook.ini`).

The companion plugin [WatcherInjector](https://github.com/Mizzlsolti/WatcherInjector)
reads this file and writes `BASE\session_stats\live.session.json` every ~100 ms,
enabling live overlays that update on every player change.

### VPinballX.ini configuration

In `VPinballX.ini`, point the plugin to the same `BasePath`:

```ini
[Plugin.Watcher]
BasePath=C:\vPinball\VPX Achievement Watcher
IniName=AW_hook.ini
```

### What the watcher writes

`AW_hook.ini` is created/updated whenever a new ROM session starts and removed
when the session ends.  A typical file looks like:

```ini
base=C:\vPinball\VPX Achievement Watcher
rom=afm_113b
nvram=C:\Visual Pinball\VPinMAME\nvram\afm_113b.nv
field=label=current_player,offset=123,size=1,mask=3,value_offset=1
field=label=player_count,offset=55,size=1,mask=0,value_offset=0
field=label=current_ball,offset=56,size=1,mask=0,value_offset=0
field=label=Balls Played,offset=200,size=1,mask=0,value_offset=0
```

Table switches update the file automatically without restarting VPX.

Many thanks 

to tomlogic    https://github.com/tomlogic/pinmame-nvram-maps 

francisdb      https://github.com/francisdb/vpxtool

emb417 https://github.com/emb417/vpc-data

VPS Team https://github.com/VirtualPinballSpreadsheet/vps-db

Team Visual Pinball 

The official Visual Pinball and PinMAME hub.

https://github.com/vpinball
