"""Offline test of VideoStudio.lua: the game's engine functions are stubbed in Lua (lupa).

    python tests/test_video_studio.py

Checks the clips (START/END cards with the clip number, the camera path, framing, HUD and camera
restored), the shots and their options, the showcase, every color (copies, one distance, the camera
carrying on round), getting round obstacles, the time-lapse, moving machines (follow, tripod), lights,
driving, the clip list (_clips_*.xml) and the autorun. lupa is Lua 5.5; the mod targets 5.1, so the
script avoids 5.2+ syntax anyway.
"""
import math, os, sys
from lupa import LuaRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
lua = LuaRuntime(unpack_returned_tuples=True)

STUBS = r'''
unpack = unpack or table.unpack
math.atan2 = math.atan2 or function(y, x) return math.atan(y, x) end
T = { now = 100.0, files = {}, nodes = {}, nextNode = 1, logs = {}, notes = {}, folders = {}, commands = {},
      xml = {}, nextXml = 1, xmlSaved = {}, loads = {}, deleted = {}, loadDelay = 0.5, rects = {}, drawn = 0 }
function getTimeSec() return T.now end
function print(s) table.insert(T.logs, s) end
T.date = "20261120_120000"
function getDate(f) return T.date end
function getUserProfileAppPath() return "C:/profile/" end
function createFolder(p) T.folders[p] = true end
T.xmlFiles = {}
function fileExists(p) return T.files[p] == true or T.xmlFiles[p] ~= nil end
function loadXMLFile(name, path)
    local values = T.xmlFiles[path]
    if values == nil then return 0 end
    local id = T.nextXml; T.nextXml = id + 1; T.xml[id] = { path = path, values = values }; return id
end
function deleteFile(p) T.xmlFiles[p] = nil; T.files[p] = nil end
function doExit() T.exited = true end
function createXMLFile(name, path, root) local id = T.nextXml; T.nextXml = id + 1; T.xml[id] = { path = path, values = {} }; return id end
function setXMLString(x, k, v) T.xml[x].values[k] = v end
function getXMLString(x, k) local o = T.xml[x]; return o ~= nil and o.values[k] or nil end
function saveXMLFile(x) T.xmlSaved[T.xml[x].path] = T.xml[x].values end
function delete(n) end
function getName(n) return "node" .. tostring(n) end
-- the engine's 2D drawing; the global table only gets it from its metatable (like the game)
setmetatable(_G, { __index = { drawFilledRect = function(x, y, w, h, r, g, b, a)
    table.insert(T.rects, { x, y, w, h, r, g, b, a }) end } })
function renderText() T.drawn = T.drawn + 1 end
function T.newNode(x, y, z) local id = T.nextNode; T.nextNode = id + 1; T.nodes[id] = {x = x or 0, y = y or 0, z = z or 0, dir = {0, 0, 1}, rot = {0, 0, 0}, visible = true}; return id end
local newNode = T.newNode
function createCamera(name, fov) local n = newNode(); T.nodes[n].fov = fov; return n end
function setFovY(n, fov) T.nodes[n].fov = fov end
function getRootNode() return 0 end
function link() end
function setFastShadowUpdate() end
function setWorldTranslation(n, x, y, z) local o = T.nodes[n]; o.x, o.y, o.z = x, y, z end
function getWorldTranslation(n) local o = T.nodes[n]; return o.x, o.y, o.z end
function getWorldRotation(n) local r = T.nodes[n].rot; return r[1], r[2], r[3] end
function setDirection(n, dx, dy, dz, ux, uy, uz) T.nodes[n].dir = {dx, dy, dz} end
-- local x = node +X (fz, -fx), z = forward (dir, flat)
function localToWorld(n, x, y, z)
    local o = T.nodes[n]; local d = o.dir; local len = math.sqrt(d[1] * d[1] + d[3] * d[3])
    local fx, fz = d[1] / len, d[3] / len
    return o.x + x * fz + z * fx, o.y + y, o.z - x * fx + z * fz
end
function worldToLocal(n, x, y, z)
    local o = T.nodes[n]; local d = o.dir; local len = math.sqrt(d[1] * d[1] + d[3] * d[3])
    local fx, fz = d[1] / len, d[3] / len
    local dx, dz = x - o.x, z - o.z
    return dx * fz - dz * fx, y - o.y, dx * fx + dz * fz
end
function localDirectionToWorld(n, x, y, z) local d = T.nodes[n].dir; return d[1], d[2], d[3] end
function getVisibility(n) return T.nodes[n].visible end
function setVisibility(n, v) T.nodes[n].visible = v end
function getTerrainHeightAtWorldPos(t, x, y, z) return 100 end
T.obstacles, T.nodeObjects = {}, {}
CollisionFlag = { DEFAULT = 1, TREE = 2, DYNAMIC_OBJECT = 4, VEHICLE = 8, BUILDING = 16, STATIC_OBJECT = 32, TERRAIN = 64 }
function raycastClosest(x, y, z, dx, dy, dz, maxDist, cb, target, mask)
    local best, bestT
    for _, o in ipairs(T.obstacles) do
        local ox, oy, oz = x - o.x, y - o.y, z - o.z
        local b = ox * dx + oy * dy + oz * dz
        local c = ox * ox + oy * oy + oz * oz - o.r * o.r
        local disc = b * b - c
        if disc >= 0 then
            local t = -b - math.sqrt(disc)
            if t >= 0 and t <= maxDist and (bestT == nil or t < bestT) then best, bestT = o, t end
        end
    end
    if best ~= nil then target[cb](target, best.id, x + dx * bestT, y + dy * bestT, z + dz * bestT, bestT) end
end
function addConsoleCommand(name, desc, fn, target) T.commands[name] = {fn, target} end
function removeConsoleCommand(name) T.commands[name] = nil end
function addModEventListener(l) T.listener = l end
MathUtil = { vector2Length = function(x, z) return math.sqrt(x * x + z * z) end }
Utils = { appendedFunction = function(a, b) return function(...) if a then a(...) end b(...) end end }
PlayerInputComponent = { registerGlobalPlayerActionEvents = function() end }
InputAction = { VS_SHOWCASE = 1, VS_ORBIT = 2, VS_FOLLOW = 3, VS_LIGHT = 4, VS_STOP = 5 }
g_inputBinding = { registerActionEvent = function(self, a, target, cb) return true, a end, setActionEventTextVisibility = function() end }
Gui = { update = function() end, draw = function() end }
FSBaseMission = { INGAME_NOTIFICATION_OK = 1, draw = function() end }
g_cameraManager = { active = 999, cams = {},
    addCamera = function(self, c) self.cams[c] = true end,
    removeCamera = function(self, c) self.cams[c] = nil end,
    getActiveCamera = function(self) return self.active end,
    setActiveCamera = function(self, c) self.active = c end }
local hud = { visible = true }
function hud:getIsVisible() return self.visible end
function hud:setIsVisible(v) self.visible = v end
T.hud = hud
WeatherType = { SUN = 1, CLOUDY = 2, RAIN = 3, SNOW = 4 }
local fogTemplate = {}
function fogTemplate:createFromTemplate() return { groundFogWeatherTypes = {} } end
T.fogUpdater = { targetFog = "gameFog" }
function T.fogUpdater:setTargetFog(fog, time) self.targetFog = fog end
T.env = { currentMonotonicDay = 10, currentDay = 10, dayTime = 8 * 3600000, daysPerPeriod = 1, currentSeason = 3,
    lighting = { update = function() end }, timeLog = {},
    weather = { fogUpdater = T.fogUpdater, seasonToFog = { [3] = fogTemplate },
                consoleCommandWeatherSet = function(self, t) T.weather = t end } }
function T.env:setEnvironmentTime(md, d, t, dpp) self.currentMonotonicDay, self.currentDay, self.dayTime = md, d, t
    table.insert(self.timeLog, t) end
VehicleLoadingState = { OK = 1, ERROR = 2 }
VehicleLoadingData = {}
VehicleLoadingData.__index = VehicleLoadingData
function VehicleLoadingData.new() return setmetatable({}, VehicleLoadingData) end
function VehicleLoadingData:setStoreItem(item) self.storeItem = item end
function VehicleLoadingData:setConfigurations(c) self.configurations = c end
function VehicleLoadingData:setPosition(x, y, z) self.pos = {x, y, z} end
function VehicleLoadingData:setRotation(x, y, z) self.rot = {x, y, z} end
function VehicleLoadingData:setIgnoreShopOffset(v) end
function VehicleLoadingData:setAddToPhysics(v) self.addToPhysics = v end
function VehicleLoadingData:setIsSaved(v) self.isSaved = v end
function VehicleLoadingData:setOwnerFarmId(id) end
function VehicleLoadingData:load(cb, target, args)
    table.insert(T.loads, { data = self, cb = cb, target = target, args = args, at = T.now + T.loadDelay })
end
function T.tickLoads()
    for i = #T.loads, 1, -1 do
        local l = T.loads[i]
        if T.now >= l.at then
            table.remove(T.loads, i)
            local node = T.newNode(l.data.pos[1], l.data.pos[2], l.data.pos[3])
            local copy = { rootNode = node, components = { { node = node } }, cfg = l.data.configurations }
            function copy:delete() table.insert(T.deleted, self) end
            function copy:setAbsolutePosition() end
            table.insert(T.copiesLoaded, copy)
            l.cb(l.target, { copy }, VehicleLoadingState.OK, l.args)
        end
    end
end
T.copiesLoaded = {}
T.storeItem = { xmlFilename = "tiger.xml", configurations = {
    baseColor = { { name = "Red", index = 1 }, { name = "Green", index = 2 }, { name = "hidden", index = 3, isSelectable = false },
                  { name = "Blue", index = 4 }, { name = "Black", index = 5 } } } }
g_storeManager = { getItemByXMLFilename = function(self, f) if f == "tiger.xml" then return T.storeItem end end }
Drivable = { CRUISECONTROL_STATE_OFF = 0, CRUISECONTROL_STATE_ACTIVE = 1 }
g_currentMission = { hud = hud, missionDynamicInfo = { isMultiplayer = false }, terrainRootNode = 5,
    missionInfo = { savegameIndex = 3, mapTitle = "Riverbend Springs" }, gameStarted = true,
    environment = T.env, placeableSystem = { placeables = {} }, vehicleSystem = { vehicles = {} },
    getNodeObject = function(self, id) return T.nodeObjects[id] end,
    addIngameNotification = function(self, kind, text) table.insert(T.notes, text) end }
g_modManager = { getActiveMods = function() return { { modName = "FS25_VideoStudio" } } end,
                 getModByName = function(self, n) return { version = "0.1.0.0" } end }
-- a harvester facing +Z at (100, 100, 50), 10 m long, 4 m wide, 4 m high, from a mod
local node = newNode(100, 100, 50)
T.tiger = { rootNode = node, components = { { node = node } }, size = { length = 10, width = 4, height = 4 },
    customEnvironment = "FS25_RopaTiger6S_ProEdition", configFileName = "tiger.xml", configurations = { baseColor = 1 } }
function T.tiger:getName() return "Tiger 6S" end
function T.tiger:getRootVehicle() return self end
function T.tiger:getChildVehicles() return { self } end
function T.tiger:getIsEnterable() return true end
function T.tiger:getOwnerFarmId() return 1 end
function T.tiger:getLastSpeed() return T.speed or 0 end
function T.tiger:getIsMotorStarted() return self.motorOn == true end
function T.tiger:startMotor() self.motorOn = true end
function T.tiger:setCruiseControlMaxSpeed(s) self.cruiseSpeed = s end
function T.tiger:setCruiseControlState(s) self.cruise = s end
function T.tiger:setLightsTypesMask(m) self.lights = m end
function T.tiger:setBeaconLightsVisibility(v) self.beacon = v end
T.tiger.spec_enterable = { cameras = { { isInside = true }, { isInside = false } } }
function T.tiger:setActiveCameraIndex(i) self.camIndex = i end
g_currentMission.vehicleSystem.vehicles = { T.tiger }
T.playerModel = true
g_localPlayer = { vehicle = T.tiger, graphicsComponent = {} }
function g_localPlayer.graphicsComponent:setModelVisibility(v) T.playerModel = v end
function g_localPlayer:getCurrentVehicle() return self.vehicle end
function g_localPlayer:getPosition() return 90, 100, 40 end
function g_localPlayer:requestToEnterVehicle(v) self.vehicle = v end
g_currentModName = "FS25_VideoStudio"
g_currentModDirectory = "C:/mods/FS25_VideoStudio/"
'''
lua.execute(STUBS)
lua.execute(open(os.path.join(ROOT, 'scripts', 'VideoStudio.lua'), encoding='utf-8').read())
T, VS, G = lua.eval('T'), lua.eval('VideoStudio'), lua.globals()

failures = []
def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        failures.append(msg)

def lua_list(t):
    return [t[i] for i in range(1, len(t) + 1)] if t is not None else []

FRAMES = []          # per frame: (marker kind or None, code or None, camera pose)
def frame():
    T.rects = lua.table()
    VS.draw(VS)
    rects = lua_list(T.rects)
    kind = code = None
    if rects:
        r = rects[0]
        kind = 'start' if (r[5], r[6], r[7]) == (1, 0, 1) else 'end' if (r[5], r[6], r[7]) == (0, 1, 1) else '?'
        bits = [int(c[5]) for c in rects[1:9]]
        code = int(''.join(map(str, bits)), 2) if len(bits) == 8 else None
    cam = VS.camera
    pose = None
    if cam is not None and G.g_cameraManager.active == cam:
        n = T.nodes[cam]
        pose = (n.x, n.y, n.z, n.dir[1], n.dir[2], n.dir[3], n.fov)
    FRAMES.append((kind, code, pose))

def run(seconds, step=1 / 60, record=True, each=None):
    for _ in range(int(round(seconds / step))):
        T.now = T.now + step
        T.tickLoads()
        if each:
            each()
        VS.update(VS, step * 1000)
        if record:
            frame()

def segments():
    """(kind, code, start, end) runs of cards in FRAMES; and the frames between START n and END n."""
    out, cur = [], None
    for i, (k, c, _) in enumerate(FRAMES):
        if cur and (k, c) == tuple(cur[:2]):
            cur[3] = i
        else:
            if cur:
                out.append(tuple(cur))
            cur = [k, c, i, i] if k else None
    if cur:
        out.append(tuple(cur))
    return out

def clips():
    segs = segments()
    out = []
    for i, s in enumerate(segs):
        if s[0] == 'start':
            for e in segs[i + 1:]:
                if e[0] == 'end' and e[1] == s[1]:
                    out.append((s[1], s[3] + 1, e[2] - 1))
                    break
    return out

def manifest():
    paths = sorted(p for p in T.xmlSaved.keys() if '_clips_' in p)
    if not paths:
        return []
    v = T.xmlSaved[paths[-1]]
    out, i = [], 0
    while v[f'clips.clip({i})#shot'] is not None:
        out.append({k.split('#')[1]: v[k] for k in v.keys() if k.startswith(f'clips.clip({i})#')})
        i += 1
    return out

def console(name, *args):
    c = T.commands[name]          # { method name, target }, like the game's console
    return c[2][c[1]](c[2], *args)

def reset_frames():
    FRAMES.clear()

def in_frame(pose, points, fov_deg, aspect=16 / 9):
    """Every point inside the picture of a camera at pose (looking along -dir)."""
    cx, cy, cz, dx, dy, dz, _ = pose
    l = math.sqrt(dx * dx + dy * dy + dz * dz)
    fwd = (-dx / l, -dy / l, -dz / l)
    up0 = (0, 1, 0)
    right = (fwd[1] * up0[2] - fwd[2] * up0[1], fwd[2] * up0[0] - fwd[0] * up0[2], fwd[0] * up0[1] - fwd[1] * up0[0])
    rl = math.sqrt(sum(c * c for c in right))
    right = tuple(c / rl for c in right)
    up = (right[1] * fwd[2] - right[2] * fwd[1], right[2] * fwd[0] - right[0] * fwd[2], right[0] * fwd[1] - right[1] * fwd[0])
    tv = math.tan(math.radians(fov_deg) / 2)
    worst = 0
    for p in points:
        v = (p[0] - cx, p[1] - cy, p[2] - cz)
        z = sum(a * b for a, b in zip(v, fwd))
        if z <= 0:
            return False, 9
        x = sum(a * b for a, b in zip(v, right)) / z / (tv * aspect)
        y = sum(a * b for a, b in zip(v, up)) / z / tv
        worst = max(worst, abs(x), abs(y))
    return worst <= 1.0, worst

TIGER_CORNERS = [(100 + dx, 100 + dy, 50 + dz) for dx in (-2, 2) for dy in (0, 4) for dz in (-5, 5)]

# ---------------------------------------------------------------- load
VS.loadMap(VS)
check(all(T.commands[c] is not None for c in ('vsShot', 'vsShowcase', 'vsStop', 'vsLight', 'vsDrive', 'vsWork', 'vsTarget')),
      'console commands registered')

# ---------------------------------------------------------------- one orbit
console('vsShot', 'orbit', 'dur=6')
check(T.hud.visible is False, 'HUD hidden while filming')
run(0.05)
check(FRAMES[-1][0] == 'start' and FRAMES[-1][1] == 1, 'START card with clip number 1 right away')
run(3.2 + 6 + 0.6)
segs = segments()
check([s[0] for s in segs] == ['start', 'end'], f'one START then one END card ({[s[0] for s in segs]})')
cl = clips()
check(len(cl) == 1 and cl[0][0] == 1, 'the clip is found between its cards')
roll = [FRAMES[i][2] for i in range(cl[0][1], cl[0][2] + 1)]
check(abs(len(roll) / 60 - 6) < 0.1, f'clip is 6 s long ({len(roll) / 60:.2f} s)')
dists = [math.dist(p[:3], (100, 102, 50)) for p in roll]
check(max(dists) - min(dists) < 0.05, f'orbit keeps one distance ({min(dists):.2f}..{max(dists):.2f} m)')
angles = [math.degrees(math.atan2(p[0] - 100, p[2] - 50)) % 360 for p in roll]
turned = sum(((angles[i + 1] - angles[i] + 180) % 360) - 180 for i in range(len(angles) - 1))
check(abs(abs(turned) - 360) < 3, f'orbit turns all the way round ({turned:.0f} degrees)')
fits = [in_frame(p, TIGER_CORNERS, 40) for p in roll[::20]]
check(all(f[0] for f in fits), f'the whole machine is in the picture all the way round (worst {max(f[1] for f in fits):.2f})')
check(max(f[1] for f in fits) > 0.6, 'and it fills the picture (not a speck)')
speeds = [math.dist(roll[i][:3], roll[i + 1][:3]) for i in range(len(roll) - 1)]
check(speeds[0] < speeds[len(speeds) // 2] / 5, 'eased: starts slowly')
check(T.hud.visible is True and G.g_cameraManager.active == 999, 'HUD and the player camera back afterwards')
m = manifest()
check(len(m) == 1 and m[0]['shot'] == 'orbit' and m[0]['code'] == '1' and m[0]['what'] == 'Tiger 6S'
      and m[0]['mod'] == 'FS25_RopaTiger6S_ProEdition', f'clip list written ({m[:1]})')
check(abs(float(m[0]['duration']) - 6) < 0.05, 'clip list has the length')
check(any('FS25_RopaTiger6S_ProEdition/_clips_' in p for p in T.xmlSaved.keys()), "clip list in the subject's mod folder")

# ---------------------------------------------------------------- quiet: other mods' drawing hidden, cards still drawn
reset_frames()
console('vsShot', 'static', 'dur=1')
run(0.2)
before = len(lua_list(T.rects))
check(FRAMES[-1][0] == 'start', 'card drawn while the drawing functions are muted')
G.drawFilledRect(0, 0, 1, 1, 1, 1, 1, 1)
check(len(lua_list(T.rects)) == before, "others' drawFilledRect does nothing during a clip")
run(5)
G.drawFilledRect(0, 0, 1, 1, 1, 1, 1, 1)
check(len(lua_list(T.rects)) > 0, 'drawFilledRect back after the run')

# ---------------------------------------------------------------- menu clips: only other mods' drawing goes
lua.execute("""
FS25_Filmed = setmetatable({}, { __index = _G })
FS25_Other = setmetatable({}, { __index = _G })
T.mods = g_modManager.getActiveMods
g_modManager.getActiveMods = function() return { { modName = "FS25_VideoStudio" }, { modName = "FS25_Filmed" }, { modName = "FS25_Other" } } end
""")
console('vsFolder', 'FS25_Filmed')
reset_frames()
console('vsShot', 'ui', 'dur=1')
run(0.5)
lua.execute("T.drawn = 0; FS25_Other.renderText(0, 0, 1, 'Courseplay'); T.otherDrew = T.drawn; FS25_Filmed.renderText(0, 0, 1, 'sheet'); renderText(0, 0, 1, 'menu')")
check(T.otherDrew == 0 and T.drawn == 2, f"menu clip: another mod's text hidden, the filmed mod's and the game's drawn ({T.otherDrew}, {T.drawn})")
run(5)
lua.execute("T.drawn = 0; FS25_Other.renderText(0, 0, 1, 'Courseplay')")
check(T.drawn == 1 and lua.eval("rawget(FS25_Other, 'renderText')") is None, "the other mod's drawing back after the clip")
reset_frames()
console('vsShot', 'ui', 'dur=1', 'keep=FS25_Other')
run(0.5)
lua.execute("T.drawn = 0; FS25_Other.renderText(0, 0, 1, 'AutoDrive HUD')")
check(lua.eval("T.drawn") == 1, "keep=: the mod named there still draws in a menu clip (a HUD the filmed mod sits on)")
run(5)
console('vsFolder')
lua.execute("g_modManager.getActiveMods = T.mods")

# ---------------------------------------------------------------- cards drawn last, after mods that draw after the mission
lua.execute("""
T.order = {}
local mine = FSBaseMission.draw
FSBaseMission.draw = function(...) mine(...) table.insert(T.order, 'modwindow') end      -- e.g. Mod Reveal
""")
reset_frames()
console('vsShot', 'static', 'dur=1')
lua.execute("T.order = {}; T.rects = {}; FSBaseMission.draw(g_currentMission)")
order = lua_list(T.order)
check(order[:1] == ['modwindow'] and len(lua_list(T.rects)) > 0, 'cards drawn after a window another mod draws after the mission')
run(6, record=False)

# ---------------------------------------------------------------- options
c = VS.makeClip(VS, 'orbit', VS.parseOptions(VS, lua.table('dur=20', 'deg=180', 'elev=8', 'dist=1.2', 'fov=30', 'dir=-1')))
check(c.dur == 20 and c['from'].a == 35 and c.to.a == 35 - 180 and c['from'].e == 8 and abs(c['from'].d - 1.2) < 1e-9 and c.fov == 30,
      'options: dur, deg, dir=-1, elev, dist, fov')
c = VS.makeClip(VS, 'arc', VS.parseOptions(VS, lua.table('side=right')))
check(c['from'].a == -15 and c.to.a == -70 and c.fixedAngle, 'side=right mirrors the arc')
c = VS.makeClip(VS, 'pushin', VS.parseOptions(VS, lua.table('a0=90', 'd1=0.8', 'ease=linear')))
check(c['from'].a == 90 and c.to.d == 0.8 and c.ease == 'linear', 'raw pose keys a0= d1=, ease')
c = VS.makeClip(VS, 'follow', VS.parseOptions(VS, lua.table('dur=0')))
check(c.untilStopped and c.dur == 300, 'dur=0: until stopped')
c = VS.makeClip(VS, 'ui', VS.parseOptions(VS, lua.table('dur=0', 'max=900', 'hand=FS25_X')))
check(c.untilStopped and c.dur == 900, 'dur=0 max=900: a long one filmed by hand (hand= is for the runner, ignored)')
lua.execute("T.help = true; function T.hud:setInputHelpVisible(v) T.help = v end")
reset_frames()
console('vsShot', 'ui', 'dur=1', 'help=0')
run(0.5)
check(lua.eval("T.help") is False, 'help=0: the F1 box hidden while the clip rolls')
run(5)
check(lua.eval("T.help") is True, 'help=0: the F1 box back after the clip')

# ---------------------------------------------------------------- showcase
reset_frames()
T.xmlSaved = lua.table()
T.date = "20261120_121000"
console('vsShowcase', 'quick')
run(60)
cl = clips()
m = manifest()
nums = [c[0] for c in cl]
check(len(cl) == 4 and nums == list(range(nums[0], nums[0] + 4)), f'showcase quick: 4 clips, numbered on ({nums})')
check([x['shot'] for x in m] == ['pushin', 'orbit', 'arc', 'drone'], 'in the clip list in order')
gaps = [cl[i + 1][1] - cl[i][2] for i in range(len(cl) - 1)]
check(all(g > 60 for g in gaps), 'cards cover the camera jump between clips (a second or more)')
check(VS.run is None and T.hud.visible, 'run over, HUD back')

# ---------------------------------------------------------------- obstacle: the arc goes round the other side
reset_frames()
T.obstacles = lua.table(lua.table())
obs = T.obstacles[1]
obs.id, obs.x, obs.y, obs.z, obs.r = 77, 106.2, 102, 57.4, 1.5   # a pole on the front-left, between the arc and the machine
console('vsShot', 'arc', 'dur=2')
run(0.1)
check(VS.clip['from'].a < 0, f"arc blocked on the left: taken on the right (from a={VS.clip['from'].a})")
check(any('in the way' in l for l in lua_list(T.logs)), 'logged what was in the way')
run(8)
T.obstacles = lua.table()

# ---------------------------------------------------------------- every color
reset_frames()
T.date = "20261120_122000"
console('vsShot', 'colors', 'dur=1.5', 'deg=40')
run(0.1)
check(T.nodes[T.tiger.rootNode].visible is False, 'the machine hidden while its copies are filmed')
run(40)
cl = clips()
m = [x for x in manifest() if x['shot'] == 'colors']
check(len(cl) == 4 and [x['color'] for x in m] == ['Red', 'Green', 'Blue', 'Black'], f"one clip per selectable color ({[x.get('color') for x in m]})")
check(len(lua_list(T.copiesLoaded)) == 4 and len(lua_list(T.deleted)) == 4, 'a copy per color, all deleted again')
check(all(not c.cfg is None for c in lua_list(T.copiesLoaded)) and [c.cfg.baseColor for c in lua_list(T.copiesLoaded)] == [1, 2, 4, 5],
      'copies in each color')
ends = [FRAMES[c[2]][2] for c in cl]
starts = [FRAMES[c[1]][2] for c in cl]
jumps = [math.dist(ends[i][:3], starts[i + 1][:3]) for i in range(len(cl) - 1)]
step = math.dist(FRAMES[cl[0][1]][2][:3], FRAMES[cl[0][1] + 1][2][:3])
check(max(jumps) < step * 3 + 0.01, f'the camera carries on where the last color stopped (jump {max(jumps):.3f} m, a frame {step:.3f} m)')
dd = [math.dist(FRAMES[c[1]][2][:3], (100, 102, 50)) for c in cl]
check(max(dd) - min(dd) < 0.01, 'one distance for every color')
check(T.nodes[T.tiger.rootNode].visible is True, 'the machine shown again')

# ---------------------------------------------------------------- time-lapse
reset_frames()
T.env.timeLog = lua.table()
T.env.dayTime = 9 * 3600000
console('vsShot', 'timelapse', 'dur=4', 'from=6', 'to=20')
run(10)
hours = [t / 3600000 for t in lua_list(T.env.timeLog)]
check(min(hours) < 6.5 and max(hours) > 19.5, f'time-lapse runs the clock from 6 to 20 ({min(hours):.1f}..{max(hours):.1f})')
check(T.env.dayTime == 9 * 3600000, 'and puts it back afterwards')

# ---------------------------------------------------------------- moving machine: follow and tripod
def drive():
    n = T.nodes[T.tiger.rootNode]
    n.z = n.z + (8 / 3.6) / 60          # 8 km/h forward (+Z)
T.speed = 8
reset_frames()
console('vsShot', 'follow', 'dur=4')
run(10, each=drive)
cl = clips()
roll = [FRAMES[i][2] for i in range(cl[0][1], cl[0][2] + 1)]
n = T.nodes[T.tiger.rootNode]
behind = [p[2] for p in roll]
check(behind[-1] > behind[0] + 5, 'follow: the camera drives along')
check(all(p[2] < 50 + 0.0 + (i / 60 + 3) * 8 / 3.6 + 10 for i, p in enumerate(roll)), 'and stays behind the machine')
reset_frames()
console('vsShot', 'flypast', 'dur=4')
run(10, each=drive)
cl = clips()
roll = [FRAMES[i][2] for i in range(cl[0][1], cl[0][2] + 1)]
check(max(math.dist(roll[0][:3], p[:3]) for p in roll) < 1e-6, 'flypast: the camera stands still')
check(abs(roll[0][1] - 101.4) < 0.75, f'on a tripod 1.4 m above the ground ({roll[0][1] - 100:.2f} m)')
dirs = [math.degrees(math.atan2(p[3], p[5])) for p in roll]
check(max(dirs) - min(dirs) > 20, 'and turns to watch it go past')
T.speed = 0

# ---------------------------------------------------------------- stop
reset_frames()
console('vsShot', 'orbit', 'dur=30')
run(5)
check(console('vsStop').startswith('Stopping'), 'vsStop while rolling')
run(1)
segs = segments()
check(segs[-1][0] == 'end' and VS.run is None, 'ends with an END card and the run is over')

# ---------------------------------------------------------------- own camera
reset_frames()
G.g_cameraManager.active = 999
console('vsShot', 'pov', 'dur=1')
run(4)
check(all(f[2] is None for f in FRAMES), 'pov: our camera never takes over')
check(any(f[0] == 'start' for f in FRAMES) and any(f[0] == 'end' for f in FRAMES), 'pov: still has its cards')

# ---------------------------------------------------------------- light, driving, working
console('vsLight', 'night')
check(T.tiger.lights == 15 and abs(T.env.dayTime / 3600000 - 22.75) < 0.01, 'night: 22:45, vehicle lights on')
console('vsLight', 'golden')
check(T.tiger.lights == 0 and abs(T.env.dayTime / 3600000 - 18.5) < 0.01, 'golden: lights off again')
console('vsLight', 'off')
check(VS.light is None, 'light off: back to the old time')
r = console('vsDrive', '8')
check(T.tiger.cruise == 1 and T.tiger.cruiseSpeed == 8 and T.tiger.motorOn, f'vsDrive 8: engine on, cruise control at 8 ({r})')
console('vsDrive', 'stop')
check(T.tiger.cruise == 0, 'vsDrive stop')

# ---------------------------------------------------------------- the sun
sun = lua.eval('T.newNode(0, 0, 0)')
T.nodes[sun].dir = lua.table(1, -0.3, 0)        # the light node's +Z points down and to +X: flipped, the sun is up towards -X
T.env.lighting.sunLightId = sun
yaw, up, how = VS.sunYaw(VS)
check(abs(math.degrees(yaw) - (-90)) < 1e-6 or abs(math.degrees(yaw) + 90) < 1e-6, f"sun direction from the light node ({math.degrees(yaw):.0f} degrees, via {how})")
check(up > 10, f"sun above the horizon ({up:.0f} degrees)")
T.env.lighting.sunLightId = None

# ---------------------------------------------------------------- vsMove: to open ground and back
lua.execute("""
function T.tiger:setAbsolutePosition(x, y, z, rx, ry, rz, parts) local n = T.nodes[self.rootNode]; n.x, n.y, n.z = x, y, z end
function T.tiger:removeFromPhysics() self.physics = false end
function T.tiger:addToPhysics() self.physics = true end
""")
n = T.nodes[T.tiger.rootNode]
home = (n.x, n.z)
T.obstacles = lua.table(lua.table())     # a shed right where it stands: the first spots that fit are further out
T.obstacles[1].id, T.obstacles[1].x, T.obstacles[1].y, T.obstacles[1].z, T.obstacles[1].r = 88, n.x, 102, n.z, 3
lua.execute("""
function overlapBox(x, y, z, rx, ry, rz, ex, ey, ez, cb, target)
    for _, o in ipairs(T.obstacles) do
        if math.abs(o.x - x) < ex + o.r and math.abs(o.z - z) < ez + o.r then target[cb](target, o.id) end
    end
end
""")
r = console('vsMove')
moved = math.dist((n.x, n.z), home)
check(r.startswith('Moved Tiger 6S') and moved >= 40 and T.tiger.physics, f'vsMove: {r} ({moved:.0f} m)')
check(console('vsMove').startswith('Already moved'), 'only once')
r = console('vsMove', 'back')
check(abs(n.x - home[0]) < 1e-6 and abs(n.z - home[1]) < 1e-6, f'vsMove back: where it was ({r})')
# a shed outside the cleared box but where the camera goes round the first place: not that place
T.obstacles[2] = lua.table()
T.obstacles[2].id, T.obstacles[2].x, T.obstacles[2].y, T.obstacles[2].z, T.obstacles[2].r = 89, home[0], 102, home[1] + 40 + 30, 3
lua.execute("VideoStudio.SPOT_VIEW = 8")
r = console('vsMove')
spot = (n.x, n.z)
check(r.startswith('Moved Tiger 6S') and math.dist(spot, (home[0], home[1] + 40)) > 1 and 'may be in some views' not in r,
      f'vsMove: not where a shed is in the camera views ({r}, at {spot[0] - home[0]:.0f}, {spot[1] - home[1]:.0f})')
console('vsMove', 'back')
T.obstacles[2].x = home[0] + 1000
lua.execute("VideoStudio.SPOT_VIEW = 3.0")
G.overlapBox = None
T.obstacles = lua.table()

# ---------------------------------------------------------------- vsMove tree: next to a tree it can reach
lua.execute("""
ClassIds = { SHAPE = 1 }
RigidBodyType = { STATIC = 1, DYNAMIC = 2 }
function getHasClassId(id, c) return T.trees[id] ~= nil end
function getSplitType(id) return 1 end
function getUserAttribute(id, name) return nil end
function getRigidBodyType(id) return T.trees[id].log and 2 or 1 end
local o = T.nodes[T.tiger.rootNode]
T.trees = {}
T.treeA = T.newNode(o.x + 30, 100, o.z)                 -- the nearest standing tree
T.treeB = T.newNode(o.x + 30, 100, o.z + 9)             -- its neighbour: the side towards it is blocked
T.logC = T.newNode(o.x + 10, 100, o.z)                  -- a felled log: not a tree to fell
T.stumpD = T.newNode(o.x + 15, 100, o.z - 3)            -- a stump left by felling (static, but cut)
T.trees[T.treeA], T.trees[T.treeB], T.trees[T.logC], T.trees[T.stumpD] = {}, {}, { log = true }, { cut = true }
function getIsSplitShapeSplit(id) return T.trees[id].cut == true end
function overlapSphere(x, y, z, r, cb, target)
    for id in pairs(T.trees) do
        local p = T.nodes[id]
        if (p.x - x) ^ 2 + (p.z - z) ^ 2 <= r * r then target[cb](target, id) end
    end
end
T.tiger.setAbsolutePosition = function(self, x, y, z, rx, ry, rz) local p = T.nodes[self.rootNode]; p.x, p.y, p.z, T.movedYaw = x, y, z, ry end
""")
r = console('vsMove', 'tree')
a, b = T.nodes[T.treeA], T.nodes[T.treeB]
d_a, d_b = math.dist((n.x, n.z), (a.x, a.z)), math.dist((n.x, n.z), (b.x, b.z))
yaw = T.movedYaw
facing = (math.sin(yaw) * (a.x - n.x) + math.cos(yaw) * (a.z - n.z)) / d_a
check(r.startswith('Moved Tiger 6S') and abs(d_a - 7) < 0.01, f'vsMove tree: 7 m from the nearest tree ({r}, {d_a:.2f} m)')
check(facing > 0.999, f'and facing it ({facing:.3f})')
check(d_b > 6.5, f'clear of the next tree ({d_b:.1f} m)')
r = console('vsMove', 'back')
check(abs(n.x - home[0]) < 1e-6 and abs(n.z - home[1]) < 1e-6, f'vsMove back after a tree: where it was ({r})')
lua.execute("T.trees = {}")
check(console('vsMove', 'tree').startswith('No tree'), 'no tree around: says so, nothing moved')
lua.execute("overlapSphere, ClassIds, RigidBodyType, getHasClassId, getSplitType, getUserAttribute, getRigidBodyType, getIsSplitShapeSplit = nil")

# ---------------------------------------------------------------- already sitting in the target; powered keys
console('vsTarget', 'Tiger')
r = console('vsEnter')
check(r.startswith('Already in Tiger') and lua.eval('g_localPlayer.vehicle == T.tiger'), f'vsEnter while sitting in the target: stays in ({r})')
lua.execute("T.tiger.motorOn = false; function T.tiger:setIsTurnedOn(on) self.turnedOn = on end")
r = console('vsPower')
check(T.tiger.motorOn and T.tiger.turnedOn, f'vsPower: engine running, machine switched on ({r})')
lua.execute("T.saved = 0; function g_currentMission:saveSavegame() T.saved = T.saved + 1 end")
r = console('vsSave')
check(lua.eval("T.saved") == 1 and r == 'Saving the game', f'vsSave: the game saves now ({r})')
lua.execute("g_currentMission.saveSavegame = nil")
lua.execute("""
T.tiger.spec_foldable = { turnOnFoldDirection = -1, foldingParts = { { animationName = 'fold' } }, foldAnimTime = 1, foldMoveDirection = 0 }
function T.tiger:setFoldDirection(d) T.foldDir = d end
""")
r = console('vsUnfold')
check(lua.eval("T.foldDir") == -1 and r.startswith('Unfolding 1 part'), f'vsUnfold: the way it works ({r})')
r = console('vsUnfold', 'fold')
check(lua.eval("T.foldDir") == 1 and r.startswith('Folding'), f'vsUnfold fold: folded again ({r})')
lua.execute("""
T.copy = { spec_foldable = { foldingParts = { { animationName = 'fold' } } }, times = {} }
function T.copy:setAnimationTime(name, t) self.times[name] = t end
function T.tiger:getAnimationTime(name) return 0 end
T.tiger.spec_foldable.foldAnimTime, T.tiger.spec_foldable.foldMoveDirection = 0, -1
VideoStudio:mirrorFold(T.copy, T.tiger)
""")
check(lua.eval("T.copy.times.fold") == 0 and lua.eval("T.copy.spec_foldable.foldMoveDirection") == -1,
      'a color copy: unfolded at once like the original')
lua.execute("T.tiger.spec_foldable = nil; T.tiger.setFoldDirection = nil; T.tiger.getAnimationTime = nil")
lua.execute("T.tiger.setIsTurnedOn = nil; T.tiger.turnedOn = nil; VideoStudio.target = nil")

# ---------------------------------------------------------------- building on foot: the player model hidden
g = G.g_localPlayer
g.vehicle = None
T.tiger.customEnvironment = None
bnode = lua.eval('T.newNode(200, 100, 200)')
bld = lua.eval('{}')
bld.rootNode = bnode
bld.customEnvironment = 'FS25_PigBarnWithRobot'
lua.execute('function T.bldName() return "Pig Barn" end')
bld.getName = lua.eval('function(self) return "Pig Barn" end')
G.g_currentMission.placeableSystem.placeables = lua.table(bld)
lua.execute('function g_localPlayer:getPosition() return 190, 100, 190 end')
G.g_currentMission.vehicleSystem.vehicles = lua.table()
reset_frames()
console('vsShot', 'drone', 'dur=1')
run(0.5)
check(T.playerModel is False, 'on foot: the player model hidden while filming')
check(VS.clip.subject.what == 'Pig Barn', 'on foot: the nearest building is filmed')
run(5)
check(T.playerModel is True, 'and shown again afterwards')

# ---------------------------------------------------------------- a building framed by its meshes, not its yard
lua.execute("""
T.children = {}
function getNumOfChildren(n) return #(T.children[n] or {}) end
function getChildAt(n, i) return T.children[n][i + 1] end
T.spheres = {}
function getShapeWorldBoundingSphere(n) local s = T.spheres[n]; if s then return s[1], s[2], s[3], s[4] end return 0, 0, 0, 0 end
local root = T.newNode(500, 100, 500)
local barn, roof, fence = T.newNode(), T.newNode(), T.newNode()
T.children[root] = { barn, roof, fence }
T.spheres[barn] = { 500, 108, 500, 20 }
T.spheres[roof] = { 500, 118, 504, 8 }
T.spheres[fence] = { 580, 101, 500, 1.5 }       -- the pasture fence, 80 m away
T.yardBarn = { rootNode = root, customEnvironment = 'FS25_X',
    spec_placement = { testAreas = {} } }
function T.yardBarn:getName() return 'Yard Barn' end
""")
corners = lua_list(VS.placeableCorners(VS, T.yardBarn))
xs = [c[1] for c in corners]
check(len(corners) == 8 and max(xs) < 520 and min(xs) > 480, f"building box from its meshes: {min(xs):.0f}..{max(xs):.0f} m, the fence 80 m off left out")
check(any('by its meshes' in l for l in lua_list(T.logs)), 'its size logged')
# with a placement area: its footprint, as high as the meshes standing on it
lua.execute('''
local s, e = T.newNode(488, 100, 485), T.newNode(512, 100, 515)
T.yardBarn.spec_placement.testAreas = { { startNode = s, endNode = e } }
''')
VS.sizeLogged = None
corners = lua_list(VS.placeableCorners(VS, T.yardBarn))
xs, ys = [c[1] for c in corners], [c[2] for c in corners]
check(min(xs) == 488 and max(xs) == 512 and max(ys) > 118, f"area footprint {min(xs):.0f}..{max(xs):.0f}, mesh height {max(ys) - 100:.0f} m")
G.getShapeWorldBoundingSphere = None

# ---------------------------------------------------------------- autorun
reset_frames()
T.xmlFiles['C:/profile/modSettings/FS25_VideoStudio/autorun.xml'] = lua.table(**{
    'autorun#savegame': '3', 'autorun#created': '20261120_120500',
    'autorun.step(0)': 'vsLight golden', 'autorun.step(1)': 'vsShot static dur=2', 'autorun.step(2)': 'wait 1',
    'autorun.step(3)': 'quit'})
T.date = "20261120_121500"
VS.autorunChecked = None
run(30)
logs = lua_list(T.logs)
check(any('autorun: started, 4 steps' in l for l in logs), 'autorun read')
check(any('step 2/4 vsShot static dur=2' in l for l in logs) and T.exited, 'autorun ran the steps, waited for the clip, quit')
check(T.xmlFiles['C:/profile/modSettings/FS25_VideoStudio/autorun.xml'] is None, 'autorun file deleted once read')

print()
if failures:
    print(f'{len(failures)} FAILED')
    sys.exit(1)
print('all ok')
