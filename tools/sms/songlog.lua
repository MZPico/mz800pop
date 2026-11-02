-- songlog.lua: MAME autoboot script for the SMS Prince of Persia (E) sound driver.
-- Logs every SN76489 write (I/O 0x40-0x7F) with its frame number, and the driver's position per frame, while a
-- chosen piece plays. The piece is started by redirecting the game's per-frame driver update call at 0x43F6
-- (`call 9680h`, executed in the VBLANK handler with the driver bank mapped at 0x8000): once, the fetched operand
-- bytes are replaced so the call goes to 0x9595 (play music A) or 0x9614 (play sfx A) with A set to the number,
-- or to 0x931A (stop music). The SMS driver re-installs its memory map now and then, which drops Lua taps, so the
-- taps are re-installed whenever a frame passes without the fetch tap firing.
-- env: PSGLOG out file, SONG number, KIND music|sfx, START frame (default 400), MAXF frames to log (default 5000)
-- log lines: "w <frame> <hex byte>" (a PSG write), "p <frame> <D0C9> <D0C8> <D0CB> <D0CC> <D0D2>" (per frame:
-- song position, row, tick, music-playing flag, sfx-playing flag), "s <frame> <kind> <n>" (the start)
local out = io.open(os.getenv("PSGLOG"), "w")
local song = tonumber(os.getenv("SONG") or "1")
local kind = os.getenv("KIND") or "music"
local start = tonumber(os.getenv("START") or "400")
local maxf = tonumber(os.getenv("MAXF") or "5000")
local cpu = manager.machine.devices[":maincpu"]
local screen = manager.machine.screens[":screen"]
local prog = cpu.spaces["program"]
local iosp = cpu.spaces["io"]
local hits, logging, pending, io_tap, fetch_tap = 0, false, nil, nil, nil
local t0 = 0
local entry = {music = 0x9595, sfx = 0x9614, stop = 0x931a}

local function install()
  if io_tap then io_tap:remove() end
  if fetch_tap then fetch_tap:remove() end
  io_tap = iosp:install_write_tap(0x40, 0x7f, "psg", function(offset, data, mask)
    if logging then out:write(string.format("w %d %02X\n", screen:frame_number() - t0, data & 0xff)) end
  end)
  fetch_tap = prog:install_read_tap(0x43f6, 0x43f8, "fetch", function(offset, data, mask)
    hits = hits + 1
    if pending then
      if offset == 0x43f6 then
        cpu.state["A"].value = pending.n
      elseif offset == 0x43f7 then
        return entry[pending.kind] & 0xff
      else
        local k = pending.kind; pending = nil
        return entry[k] >> 8
      end
    end
  end)
end
install()

emu.register_frame_done(function()
  local f = screen:frame_number()
  if f > 0 and hits == 0 then install() end
  hits = 0
  if f == start - 60 and kind == "sfx" then pending = {kind = "stop", n = 0} end
  if f == start then
    pending = {kind = kind, n = song}; logging = true; t0 = f
    out:write(string.format("s %d %s %d\n", 0, kind, song))
  end
  if logging then
    out:write(string.format("p %d %d %d %d %d %d\n", f - t0, prog:read_u8(0xd0c9), prog:read_u8(0xd0c8),
      prog:read_u8(0xd0cb), prog:read_u8(0xd0cc), prog:read_u8(0xd0d2)))
    if f % 250 == 0 then out:flush() end
    if f - t0 >= maxf then out:close(); logging = false; manager.machine:exit() end
  end
end)
emu.add_machine_stop_notifier(function() if logging then out:close() end end)
