-- DTM Video Studio: cinematic camera moves for mod videos (YouTube, websites), played by the game.
--
-- Right Shift + 1  Showcase: a set of camera moves around what you sit in (or the target)
-- Right Shift + 2  Orbit: one slow 360 degree orbit
-- Right Shift + 3  Follow: a chase camera while you drive; again to stop
-- Right Shift + 4  Light: golden hour, morning mist, midday, overcast, dawn, night, then the old time
-- Right Shift + 0  Stop: ends the clip now and clears the queue
--
-- The game doesn't record video: tools/fs25_video.py records the game window (and the sound) and
-- cuts the clips out. How it finds them: while the camera gets into place and the textures stream
-- in, the screen shows a START card (magenta, the clip number as 8 black/white cells along the
-- bottom). Then the camera moves; at the end an END card (cyan, the same cells). The cut takes
-- exactly the frames between the two cards, so it never depends on log timing.
--
-- Each run of clips writes _clips_<time>.xml into modSettings/FS25_VideoStudio/<mod name>/: what
-- each clip is (shot, subject, light, color, length), which the tools use to name and arrange them.
-- Single player only (modDesc).

VideoStudio = {}
local VS = VideoStudio

VS.MOD_NAME = g_currentModName
VS.MOD_DIR = g_currentModDirectory

VS.ASPECT = 16 / 9
VS.FOV = 40                  -- degrees (vertical); lower looks more "filmed", less "game"
VS.FILL = 0.74               -- how much of the picture the machine fills (edge to edge = 1); video wants room
VS.MIN_DISTANCE = 3          -- metres
VS.CLEARANCE = 0.7           -- metres the camera stays above the ground
VS.SETTLE_FIRST_MS = 3000    -- first clip of a run: textures, shadows, LODs, TAA
VS.SETTLE_MS = 1600          -- later clips (the camera jumped: the new view streams in)
VS.END_MS = 450              -- END card
VS.LOAD_TIMEOUT_MS = 30000   -- loading a color copy
VS.MAX_CLIP_S = 300          -- an open-ended clip (follow until stopped) ends after this
VS.MAX_COLORS = 12
VS.PLACEABLE_RADIUS = 18
VS.MAX_PLACEABLE_DISTANCE = 150
VS.MAX_VEHICLE_DISTANCE = 40
VS.LIST_RADIUS = 150
VS.MAX_LIST = 40
VS.CROWN = 4.5               -- metres a tree's branches reach from its trunk (crowns have no collision)
VS.avoidObstacles = true
VS.quietEnabled = true
VS.hidePlayer = true

-- START/END cards: drawn with the engine's own functions, kept before quiet mode swaps the global ones.
-- A white image overlay (renderOverlay, what the game's HUD draws with) first, drawFilledRect else.
local rawDrawRect = drawFilledRect
local rawRenderOverlay = renderOverlay
local rawSetOverlayColor = setOverlayColor
VS.MARK = { start = { 1, 0, 1 }, ["end"] = { 0, 1, 1 } }

-- Easing: t (0..1) -> progress (0..1)
VS.EASES = {
    linear = function(t) return t end,
    sine = function(t) return 0.5 - 0.5 * math.cos(math.pi * t) end,
    inout = function(t) if t < 0.5 then return 4 * t * t * t end return 1 - ((-2 * t + 2) ^ 3) / 2 end,
    out = function(t) return 1 - (1 - t) ^ 3 end,
    ["in"] = function(t) return t * t * t end,
    smooth = function(t) return t * t * t * (t * (t * 6 - 15) + 10) end,
}

-- The shots. A pose is spherical around the look point: a = angle off the front (degrees; 90 = the
-- machine's left side, 180 the rear), e = elevation (degrees up), d = distance in "framed"
-- units (1 = the whole machine fills FILL of the picture from there), lx/ly/lz = look point off the
-- middle in half-sizes of the machine (x left, y up, z forward), sx/sy/sz = camera slid along the
-- machine's axes in framed units (st = 1: the look point slides too), fov in degrees.
-- `from` is the pose at the start, `to` the changes at the end. anchor "world" keeps the camera
-- where the shot started (a tripod) while it still looks at the machine; smooth = seconds of lag
-- (a camera operator, for moving machines).
VS.SHOTS = {
    orbit    = { dur = 16, ease = "sine", from = { a = 35, e = 14, d = 1.0 }, to = { a = 395 }, text = "360 degree orbit" },
    arc      = { dur = 9, ease = "sine", from = { a = 15, e = 4, d = 0.95 }, to = { a = 70 }, text = "low hero arc" },
    pushin   = { dur = 8, ease = "out", from = { a = 35, e = 9, d = 1.75 }, to = { d = 1.0 }, text = "push in" },
    pullback = { dur = 9, ease = "inout", from = { a = 28, e = 6, d = 0.42, lz = 0.7, ly = 0.15 },
                 to = { a = 40, e = 12, d = 1.1, lz = 0, ly = 0 }, text = "reveal from a detail" },
    crane    = { dur = 9, ease = "sine", from = { a = 30, e = 2, d = 1.0 }, to = { e = 40, d = 1.25 }, text = "crane up" },
    drone    = { dur = 12, ease = "sine", from = { a = -25, e = 52, d = 2.5 }, to = { a = 65, e = 36, d = 1.45 }, text = "drone" },
    topdown  = { dur = 9, ease = "sine", from = { a = 0, e = 84, d = 1.45 }, to = { a = 40, d = 1.05 }, text = "top-down" },
    front    = { dur = 7, ease = "out", from = { a = 0, e = 3, d = 1.6 }, to = { d = 0.95 }, text = "head-on push" },
    rear     = { dur = 8, ease = "sine", from = { a = 150, e = 10, d = 1.0 }, to = { a = 210 }, text = "rear arc" },
    flyby    = { dur = 8, ease = "linear", from = { a = 90, e = 8, d = 1.0, sz = 0.9 }, to = { sz = -0.9 }, text = "fly-by" },
    pass     = { dur = 9, ease = "linear", from = { a = 90, e = 10, d = 0.5, sz = 0.55, st = 1 }, to = { sz = -0.55 }, text = "detail pass" },
    static   = { dur = 8, ease = "linear", from = { a = 35, e = 12, d = 1.0 }, text = "locked-off view" },
    timelapse = { dur = 12, ease = "linear", from = { a = 35, e = 14, d = 1.15 }, to = { d = 1.05 }, text = "time-lapse",
                  hours = { 6, 21 } },
    -- for a moving machine (vsDrive, or you drive)
    follow   = { dur = 12, ease = "linear", from = { a = 180, e = 15, d = 1.2 }, smooth = 0.45, text = "chase camera" },
    side     = { dur = 10, ease = "linear", from = { a = 90, e = 6, d = 1.05 }, smooth = 0.35, text = "tracking alongside" },
    lead     = { dur = 10, ease = "linear", from = { a = 22, e = 8, d = 1.25 }, smooth = 0.45, text = "leading in front" },
    flypast  = { dur = 10, ease = "linear", tripod = true, text = "drive-past from a tripod" },
    -- no camera of ours
    pov      = { dur = 10, own = true, text = "your own camera (cab, outside), no HUD" },
    ui       = { dur = 8, own = true, hud = true, text = "the screen as it is: menus and HUD" },
    colors   = { dur = 3, ease = "linear", from = { a = 30, e = 10, d = 1.05 }, sweep = 70, colors = true,
                 text = "every color, the camera moving on" },
}
VS.SHOT_ORDER = { "orbit", "arc", "pushin", "pullback", "crane", "drone", "topdown", "front", "rear", "flyby", "pass",
    "static", "timelapse", "follow", "side", "lead", "flypast", "pov", "ui", "colors" }

-- vsShowcase sets. A building has no front worth an arc at ground level.
VS.SHOWCASES = {
    vehicle = { "pushin", "orbit", "pullback", "arc", "crane", "flyby", "rear", "drone" },
    quick = { "pushin", "orbit", "arc", "drone" },
    building = { "pushin e0=8 d0=1.5 d1=0.9", "orbit e0=12 dist=0.95 dur=20", "arc dist=0.9", "crane e1=30",
                 "flyby e0=8 dist=0.9", "drone d0=1.6 d1=1.15 e0=38 e1=28" },
    work = { "follow", "side", "lead", "flypast", "side angle=-90", "drone" },
}

-- Right Shift + 4 goes through these, then back to the game's own time (hours are game time)
VS.LIGHTS = {
    { id = "golden",   hour = 18.5,  weather = "SUN",    text = "golden hour" },
    { id = "morning",  hour = 7.25,  weather = "SUN",    text = "morning mist", fog = true },
    { id = "midday",   hour = 12.5,  weather = "SUN",    text = "midday sun" },
    { id = "overcast", hour = 13.0,  weather = "CLOUDY", text = "overcast, soft light" },
    { id = "dawn",     hour = 6.0,   weather = "SUN",    text = "dawn" },
    { id = "night",    hour = 22.75, weather = "SUN",    text = "night, vehicle lights on", lights = true },
}
VS.MIST = {
    groundFogCoverageEdge0 = 0.05, groundFogCoverageEdge1 = 0.9, groundFogExtraHeight = 20,
    groundFogGroundLevelDensity = 0.7, heightFogMaxHeight = 600, heightFogGroundLevelDensity = 0.35,
}

VS.COLOR_CONFIGS = { "baseColor", "baseMaterial", "designColor", "designMaterial", "rimColor", "wrappingColor" }
VS.BODY_WORDS = { "body", "paint", "karosserie", "lackierung" }
VS.NOT_BODY_WORDS = { "hub", "rim", "wheel", "tire", "tyre", "felge", "nabe", "seat", "sitz", "interior",
    "innen", "leather", "leder", "light", "beacon", "glass" }

VS.queue = {}          -- clips still to play: { shot = id, opts = { ... }, text = "orbit dur=10" }
VS.run = nil           -- the run of clips: HUD, camera, quiet, the clips done
VS.clip = nil          -- the clip playing
VS.marker = nil        -- { kind = "start"|"end", code = 1..255 } while a card shows
VS.clipNumber = 0
VS.target = nil
VS.forcedFolder = nil
VS.light = nil
VS.lightSaved = nil
VS.fov = nil           -- vsFov: default field of view for every shot


local function log(fmt, ...)
    print(string.format("[VideoStudio] " .. fmt, ...))
end

local function now()
    return getTimeSec() * 1000     -- real time: the recording runs in real time
end

local function notify(text)
    if g_currentMission ~= nil and g_currentMission.addIngameNotification ~= nil then
        pcall(g_currentMission.addIngameNotification, g_currentMission, FSBaseMission.INGAME_NOTIFICATION_OK, text)
    end
end

local function safeName(name)
    name = tostring(name or "misc"):gsub("[^%w%-_]", "_")
    if name == "" then name = "misc" end
    return name
end

local function vehicleName(v)
    if v ~= nil and v.getName ~= nil then
        local ok, name = pcall(v.getName, v)
        if ok and name ~= nil then return tostring(name) end
    end
    return "vehicle"
end

local function placeableName(p)
    if p ~= nil and p.getName ~= nil then
        local ok, name = pcall(p.getName, p)
        if ok and name ~= nil then return tostring(name) end
    end
    return "building"
end

local function trueGlobals()
    local ok, g = pcall(getfenv, 0)
    if ok and type(g) == "table" then return g end
    return _G
end

local function removeFile(path)
    local f = trueGlobals().deleteFile or deleteFile
    if f ~= nil then pcall(f, path) end
end

local function isGone(o)
    return o == nil or o.isDeleted == true or o.rootNode == nil
end

local function lerp(a, b, t) return a + (b - a) * t end

local function copyTable(t)
    local out = {}
    for k, v in pairs(t or {}) do out[k] = type(v) == "table" and copyTable(v) or v end
    return out
end

local function ground(x, z)
    if g_currentMission == nil or g_currentMission.terrainRootNode == nil then return -math.huge end
    return getTerrainHeightAtWorldPos(g_currentMission.terrainRootNode, x, 0, z)
end

function VS:getBaseDir()
    return getUserProfileAppPath() .. "modSettings/" .. self.MOD_NAME .. "/"
end


-- ------------------------------------------------------------------ targets (as Screenshot Studio)
function VS:findObjects(text)
    local player = g_localPlayer
    if player == nil or g_currentMission == nil then return {} end
    local px, _, pz = player:getPosition()
    local want = text ~= nil and text ~= "" and text:lower() or nil
    local list = {}
    local function add(kind, obj, name)
        if want ~= nil then
            local file = tostring(obj.configFileName or ""):match("([^/\\]+)$") or ""
            local hay = (name .. " " .. tostring(obj.customEnvironment or "") .. " " .. file):lower()
            if not hay:find(want, 1, true) then return end
        end
        local x, _, z = getWorldTranslation(obj.rootNode)
        local on
        if kind == "vehicle" and obj.getRootVehicle ~= nil then
            local root = obj:getRootVehicle()
            if root ~= nil and root ~= obj then on = vehicleName(root) end
        end
        table.insert(list, { kind = kind, obj = obj, name = name, mod = obj.customEnvironment or "basegame",
            dist = MathUtil.vector2Length(x - px, z - pz), on = on })
    end
    local vehicles = g_currentMission.vehicleSystem
    for _, v in ipairs(vehicles ~= nil and vehicles.vehicles or {}) do
        if not isGone(v) and not v.isPallet then add("vehicle", v, vehicleName(v)) end
    end
    local placeables = g_currentMission.placeableSystem
    for _, p in ipairs(placeables ~= nil and placeables.placeables or {}) do
        if not isGone(p) then add("building", p, placeableName(p)) end
    end
    table.sort(list, function(a, b) return a.dist < b.dist end)
    return list
end

function VS:getTarget()
    local t = self.target
    if t == nil then return nil end
    if isGone(t.vehicle or t.placeable) then
        log("Target %s is gone: back to what you sit in or stand next to", tostring(t.name))
        self.target = nil
        return nil
    end
    return t
end

function VS:setTarget(text)
    if text == nil or text == "" then
        self.target = nil
        return "Target: what you sit in, or the nearest vehicle/building"
    end
    local found = self:findObjects(text)
    -- a hitched one first (a header on its harvester is what a video wants), then the nearest
    table.sort(found, function(a, b)
        if (a.on ~= nil) ~= (b.on ~= nil) then return a.on ~= nil end
        return a.dist < b.dist
    end)
    local best = found[1]
    if best == nil then
        local near = {}
        for i, o in ipairs(self:findObjects(nil)) do
            if i > 8 then break end
            table.insert(near, string.format("%s (%s, %.0f m)", o.name, o.mod, o.dist))
        end
        log("vsTarget %s: nothing with that in its name, mod or file. Nearest: %s", text, table.concat(near, "; "))
        return string.format("Nothing called '%s'. vsList shows the names near you.", text)
    end
    self.target = best.kind == "vehicle" and { vehicle = best.obj, name = best.name }
        or { placeable = best.obj, name = best.name }
    local more = #found > 1 and string.format(" (%d more match; the nearest wins)", #found - 1) or ""
    return string.format("Target: %s %s (%s, %.0f m%s)%s", best.kind, best.name, best.mod, best.dist,
        best.on ~= nil and (", on " .. best.on) or "", more)
end

function VS:listObjects(text)
    local found = self:findObjects(text)
    local shown = 0
    for _, o in ipairs(found) do
        if (text ~= nil and text ~= "") or o.dist <= self.LIST_RADIUS then
            shown = shown + 1
            if shown <= self.MAX_LIST then
                log("%5.0f m  %-8s %s (%s)%s", o.dist, o.kind, o.name, o.mod, o.on ~= nil and ("  on " .. o.on) or "")
            end
        end
    end
    if shown == 0 then
        return (text ~= nil and text ~= "") and ("Nothing called '" .. text .. "'")
            or string.format("Nothing within %d m", self.LIST_RADIUS)
    end
    return string.format("%d found; vsTarget <part of a name> picks one", shown)
end

function VS:getSeatVehicle()
    local player = g_localPlayer
    return player ~= nil and player.getCurrentVehicle ~= nil and player:getCurrentVehicle() or nil
end

function VS:groupOf(vehicle, subject)
    if vehicle == nil then return nil end
    local root = vehicle.getRootVehicle ~= nil and vehicle:getRootVehicle() or vehicle
    local list, seen = {}, {}
    local function add(v)
        if v ~= nil and not seen[v] and v.rootNode ~= nil then
            seen[v] = true
            table.insert(list, v)
        end
    end
    add(root)
    if root.getChildVehicles ~= nil then
        for k, v in pairs(root:getChildVehicles() or {}) do add(type(v) == "table" and v or (type(k) == "table" and k or nil)) end
    end
    if subject == nil then
        subject = root
        for _, v in ipairs(list) do
            if v.customEnvironment ~= nil and (subject.customEnvironment == nil or v ~= root) then subject = v end
        end
    end
    return { root = root, list = list, subject = subject, what = vehicleName(subject) }
end

function VS.subjectSet(list)
    local set = {}
    for _, o in ipairs(list) do
        set[o] = true
        if o.getRootVehicle ~= nil then
            local ok, root = pcall(o.getRootVehicle, o)
            if ok and root ~= nil then set[root] = true end
        end
        if o.getChildVehicles ~= nil then
            local ok, children = pcall(o.getChildVehicles, o)
            for k, c in pairs(ok and type(children) == "table" and children or {}) do
                if type(c) == "table" then set[c] = true end
                if type(k) == "table" then set[k] = true end
            end
        end
    end
    return set
end

function VS:nearest(list, maxDist)
    local player = g_localPlayer
    if player == nil then return nil end
    local px, _, pz = player:getPosition()
    local best, bestScore
    for _, o in ipairs(list) do
        if not isGone(o) then
            local x, _, z = getWorldTranslation(o.rootNode)
            local d = MathUtil.vector2Length(x - px, z - pz)
            local score = d + (o.customEnvironment == nil and 50 or 0)     -- mods first
            if d < maxDist and (bestScore == nil or score < bestScore) then best, bestScore = o, score end
        end
    end
    return best
end


-- ------------------------------------------------------------------ the subject's box
-- A vehicle's size box (8 corners around its root node) plus where it really reaches unfolded:
-- work areas and parts (Screenshot Studio's framing)
function VS:boxCorners(v)
    local s = v.size or {}
    local w, l, h = s.width or 3, s.length or 4, s.height or 3
    local wo, lo, ho = s.widthOffset or 0, s.lengthOffset or 0, s.heightOffset or 0
    local list = {}
    for _, dx in ipairs({ -w / 2, w / 2 }) do
        for _, dz in ipairs({ -l / 2, l / 2 }) do
            for _, dy in ipairs({ 0, h }) do
                local x, y, z = localToWorld(v.rootNode, dx + wo, dy + ho, dz + lo)
                table.insert(list, { x, y, z })
            end
        end
    end
    return list
end

function VS:reachPoints(v)
    local pts = {}
    local up = math.min(3, (v.size ~= nil and v.size.height) or 2)
    local function add(node)
        if node ~= nil and node ~= 0 then
            local ok, x, y, z = pcall(getWorldTranslation, node)
            if ok and x ~= nil then
                table.insert(pts, { x, y, z })
                table.insert(pts, { x, y + up, z })
            end
        end
    end
    local unfolded = true
    if v.getIsUnfolded ~= nil then
        local ok, u = pcall(v.getIsUnfolded, v)
        unfolded = not ok or u ~= false
    end
    local spec = v.spec_workArea
    for _, area in ipairs(unfolded and spec ~= nil and spec.workAreas or {}) do
        add(area.start); add(area.width); add(area.height)
    end
    for _, c in ipairs(v.components or {}) do add(c.node) end
    return pts
end

function VS:cornersOf(vehicles)
    local all = {}
    for _, v in ipairs(vehicles) do
        for _, c in ipairs(self:boxCorners(v)) do table.insert(all, c) end
        for _, p in ipairs(self:reachPoints(v)) do table.insert(all, p) end
    end
    return all
end

-- The building itself, from its visible meshes: the biggest one (the barn, the silo) and those close
-- to it, as a box. Placement test areas can include a whole yard or pasture: the camera then stood so
-- far back that the building was a speck.
VS.SHAPE_NODES_MAX = 6000
function VS:placeableShapeCorners(p)
    if getShapeWorldBoundingSphere == nil or getNumOfChildren == nil or getChildAt == nil then return {}, 0, nil end
    local isShape = function(node)
        if getHasClassId ~= nil and ClassIds ~= nil and ClassIds.SHAPE ~= nil then
            local ok, yes = pcall(getHasClassId, node, ClassIds.SHAPE)
            return ok and yes
        end
        return true
    end
    local spheres, stack, seen = {}, { p.rootNode }, 0
    while #stack > 0 and seen < self.SHAPE_NODES_MAX do
        local node = table.remove(stack)
        seen = seen + 1
        local visible = getVisibility == nil or getVisibility(node)
        if visible then
            if isShape(node) then
                local ok, x, y, z, r = pcall(getShapeWorldBoundingSphere, node)
                if ok and r ~= nil and r > 0.3 and r < 120 then table.insert(spheres, { x, y, z, r }) end
            end
            local okn, n = pcall(getNumOfChildren, node)
            for i = 0, (okn and n or 0) - 1 do table.insert(stack, getChildAt(node, i)) end
        end
    end
    if #spheres == 0 then return {}, 0, nil end
    table.sort(spheres, function(a, b) return a[4] > b[4] end)
    local main = spheres[1]
    local lo = { main[1] - main[4] * 0.75, main[2] - main[4] * 0.75, main[3] - main[4] * 0.75 }
    local hi = { main[1] + main[4] * 0.75, main[2] + main[4] * 0.75, main[3] + main[4] * 0.75 }
    for i = 2, #spheres do
        local sp = spheres[i]
        local d = math.sqrt((sp[1] - main[1]) ^ 2 + (sp[2] - main[2]) ^ 2 + (sp[3] - main[3]) ^ 2)
        if d < main[4] * 1.5 then
            local r = sp[4] * 0.75
            lo[1], lo[2], lo[3] = math.min(lo[1], sp[1] - r), math.min(lo[2], sp[2] - r), math.min(lo[3], sp[3] - r)
            hi[1], hi[2], hi[3] = math.max(hi[1], sp[1] + r), math.max(hi[2], sp[2] + r), math.max(hi[3], sp[3] + r)
        end
    end
    local g = ground((lo[1] + hi[1]) / 2, (lo[3] + hi[3]) / 2)
    lo[2] = math.max(lo[2], g)
    local corners = {}
    for _, x in ipairs({ lo[1], hi[1] }) do
        for _, y in ipairs({ lo[2], hi[2] }) do
            for _, z in ipairs({ lo[3], hi[3] }) do table.insert(corners, { x, y, z }) end
        end
    end
    return corners, #spheres, spheres
end

local function boxSize(corners)
    local lo, hi = { math.huge, math.huge, math.huge }, { -math.huge, -math.huge, -math.huge }
    for _, c in ipairs(corners) do
        for i = 1, 3 do lo[i], hi[i] = math.min(lo[i], c[i]), math.max(hi[i], c[i]) end
    end
    if #corners == 0 then return "none" end
    return string.format("%.0fx%.0fx%.0f m", hi[1] - lo[1], hi[3] - lo[3], hi[2] - lo[2])
end

-- A building's box: the footprint of its placement area (the building itself; Screenshot Studio frames
-- by it too) as high as its own meshes standing on that footprint reach. Meshes alone take in yards
-- and pastures; the area alone is flat. No area: the meshes; neither: vsRadius / a default size.
function VS:placeableCorners(p)
    if self.placeableRadius ~= nil then return self:placeableAreaCorners(p, true) end
    local areas = self:placeableAreaCorners(p)
    local shapes, n, spheres = self:placeableShapeCorners(p)
    local corners, how = areas, "placement area"
    if #areas > 0 and spheres ~= nil then
        local lo, hi = { math.huge, math.huge, math.huge }, { -math.huge, -math.huge, -math.huge }
        for _, c in ipairs(areas) do
            for i = 1, 3 do lo[i], hi[i] = math.min(lo[i], c[i]), math.max(hi[i], c[i]) end
        end
        local top = hi[2]
        for _, sp in ipairs(spheres) do
            if sp[1] >= lo[1] and sp[1] <= hi[1] and sp[3] >= lo[3] and sp[3] <= hi[3] then
                top = math.max(top, sp[2] + sp[4] * 0.6)
            end
        end
        top = math.min(top, lo[2] + 60)
        corners = {}
        for _, x in ipairs({ lo[1], hi[1] }) do
            for _, y in ipairs({ lo[2], top }) do
                for _, z in ipairs({ lo[3], hi[3] }) do table.insert(corners, { x, y, z }) end
            end
        end
        how = "placement area, meshes' height"
    elseif #areas == 0 and #shapes > 0 then
        corners, how = shapes, "meshes"
    elseif #areas == 0 then
        corners, how = self:placeableAreaCorners(p, true), "default size"
    end
    self.sizeLogged = self.sizeLogged or {}
    if not self.sizeLogged[p] then
        self.sizeLogged[p] = true
        log("%s: framed as %s by its %s (meshes alone: %s)", placeableName(p), boxSize(corners), how, boxSize(shapes))
    end
    return corners
end

function VS:placeableAreaCorners(p, radiusOnly)
    local spec = p.spec_placement
    local corners = {}
    for _, area in ipairs((not radiusOnly) and spec ~= nil and spec.testAreas or {}) do
        local s, e = area.startNode, area.endNode
        if s ~= nil and e ~= nil and worldToLocal ~= nil then
            local ex, ey, ez = worldToLocal(s, getWorldTranslation(e))
            if math.abs(ey) < 1 then
                ey = math.min(18, math.max(4, 0.45 * math.max(math.abs(ex), math.abs(ez))))
            end
            for _, x in ipairs({ 0, ex }) do
                for _, y in ipairs({ 0, ey }) do
                    for _, z in ipairs({ 0, ez }) do
                        local wx, wy, wz = localToWorld(s, x, y, z)
                        table.insert(corners, { wx, wy, wz })
                    end
                end
            end
        end
    end
    if #corners == 0 and (radiusOnly or self.placeableRadius ~= nil) then
        local x, y, z = getWorldTranslation(p.rootNode)
        local r = self.placeableRadius or self.PLACEABLE_RADIUS
        for _, dx in ipairs({ -r, r }) do
            for _, dz in ipairs({ -r, r }) do
                table.insert(corners, { x + dx, y, z + dz })
                table.insert(corners, { x + dx, y + r * 0.8, z + dz })
            end
        end
    end
    return corners
end

-- The subject: what you sit in (an implement from a mod wins as its name), the target, or on foot
-- the nearest vehicle (40 m) or building (150 m). Its box is kept in its own frame (x left, y up,
-- z forward, around the middle of the box), so camera moves follow it when it drives.
function VS:getSubject()
    local t = self:getTarget()
    if t ~= nil and t.vehicle ~= nil then return self:vehicleSubject(self:groupOf(t.vehicle, t.vehicle)) end
    if t ~= nil and t.placeable ~= nil then return self:placeableSubject(t.placeable) end
    local seat = self:getSeatVehicle()
    if seat ~= nil then return self:vehicleSubject(self:groupOf(seat)) end
    local vs = g_currentMission ~= nil and g_currentMission.vehicleSystem or nil
    local list = {}
    for _, v in ipairs(vs ~= nil and vs.vehicles or {}) do
        if not v.isPallet and v.configFileName ~= nil then table.insert(list, v) end
    end
    local v = self:nearest(list, self.MAX_VEHICLE_DISTANCE)
    if v ~= nil then return self:vehicleSubject(self:groupOf(v)) end
    local ps = g_currentMission ~= nil and g_currentMission.placeableSystem or nil
    local p = self:nearest(ps ~= nil and ps.placeables or {}, self.MAX_PLACEABLE_DISTANCE)
    if p ~= nil then return self:placeableSubject(p) end
    return nil
end

function VS:vehicleSubject(group)
    if group == nil then return nil end
    local s = self:subjectFrom(group.root.rootNode, self:cornersOf(group.list))
    s.kind, s.group, s.vehicle = "vehicle", group, group.root
    s.what = group.what
    s.mod = group.subject.customEnvironment or "basegame"
    s.subjects = VS.subjectSet(group.list)
    return s
end

function VS:placeableSubject(p)
    local s = self:subjectFrom(p.rootNode, self:placeableCorners(p))
    s.kind, s.placeable = "building", p
    s.what = placeableName(p)
    s.mod = p.customEnvironment or "basegame"
    s.subjects = { [p] = true }
    return s
end

-- the frame of `node` now: forward and left on the flat, and where the box's middle is
function VS:frameOf(s)
    local fx, _, fz = localDirectionToWorld(s.node, 0, 0, 1)
    local len = math.sqrt(fx * fx + fz * fz)
    if len < 1e-6 then fx, fz, len = 0, 1, 1 end
    fx, fz = fx / len, fz / len
    local cx, cy, cz = localToWorld(s.node, s.mid[1], s.mid[2], s.mid[3])
    return { cx = cx, cy = cy, cz = cz, fx = fx, fz = fz, lx = fz, lz = -fx }
end

function VS:toWorld(f, x, y, z)
    return f.cx + x * f.lx + z * f.fx, f.cy + y, f.cz + x * f.lz + z * f.fz
end

function VS:toLocal(f, wx, wy, wz)
    local dx, dz = wx - f.cx, wz - f.cz
    return dx * f.lx + dz * f.lz, wy - f.cy, dx * f.fx + dz * f.fz
end

function VS:subjectFrom(node, worldCorners)
    local s = { node = node, mid = { 0, 0, 0 } }
    local lo, hi = { math.huge, math.huge, math.huge }, { -math.huge, -math.huge, -math.huge }
    for _, c in ipairs(worldCorners) do
        for i = 1, 3 do lo[i], hi[i] = math.min(lo[i], c[i]), math.max(hi[i], c[i]) end
    end
    if #worldCorners == 0 then
        local x, y, z = getWorldTranslation(node)
        lo, hi = { x - 2, y, z - 2 }, { x + 2, y + 3, z + 2 }
    end
    -- the middle of the box, kept in the node's own space (it moves and turns with the node)
    local mx, my, mz = (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2, (lo[3] + hi[3]) / 2
    s.mid = { worldToLocal(node, mx, my, mz) }
    local f = self:frameOf(s)
    -- the corners in the subject's frame, and its half sizes
    local local_ = {}
    local half = { 0.5, 0.5, 0.5 }
    for _, c in ipairs(worldCorners) do
        local x, y, z = self:toLocal(f, c[1], c[2], c[3])
        table.insert(local_, { x, y, z })
        half[1], half[2], half[3] = math.max(half[1], math.abs(x)), math.max(half[2], math.abs(y)), math.max(half[3], math.abs(z))
    end
    if #local_ == 0 then
        for _, dx in ipairs({ -2, 2 }) do for _, dy in ipairs({ -1.5, 1.5 }) do for _, dz in ipairs({ -2, 2 }) do
            table.insert(local_, { dx, dy, dz })
        end end end
        half = { 2, 1.5, 2 }
    end
    s.corners, s.half, s.worldCorners = local_, half, worldCorners
    return s
end


-- ------------------------------------------------------------------ framing and poses
-- How far back the camera must be, looking from angle a / elevation e (degrees) at the middle, so
-- every corner fits FILL of the 16:9 picture with this field of view
function VS:fitDistance(s, a, e, fov)
    local ar, er = math.rad(a), math.rad(e)
    local sa, ca, se, ce = math.sin(ar), math.cos(ar), math.sin(er), math.cos(er)
    local ux, uy, uz = sa * ce, se, ca * ce            -- from the middle to the camera
    local rx, rz = ca, -sa                              -- across the picture (horizontal)
    local vx, vy, vz = -se * sa, ce, -se * ca           -- up in the picture
    local tanV = math.tan(math.rad(fov) / 2) * self.FILL
    local tanH = tanV * self.ASPECT
    local d = self.MIN_DISTANCE
    for _, c in ipairs(s.corners) do
        local along = c[1] * ux + c[2] * uy + c[3] * uz
        d = math.max(d, along + math.abs(c[1] * rx + c[3] * rz) / tanH, along + math.abs(c[1] * vx + c[2] * vy + c[3] * vz) / tanV)
    end
    return d
end

-- the pose at progress p (0..1, already eased): from, with to's changes blended in
function VS:poseAt(clip, p)
    local from, to = clip.from, clip.to
    local out = {}
    for k, v in pairs(from) do
        local w = to[k]
        out[k] = (type(v) == "number" and type(w) == "number") and lerp(v, w, p) or v
    end
    -- only in `to`: from what the pose would be without it
    local default = { d = 1, fov = clip.fov }
    for k, w in pairs(to) do
        if out[k] == nil then out[k] = type(w) == "number" and lerp(default[k] or 0, w, p) or w end
    end
    return out
end

-- camera and look point in the subject's frame (metres) for a pose
function VS:poseLocal(clip, q)
    local s, D = clip.subject, clip.D
    local lx = (q.lx or 0) * s.half[1]
    local ly = (q.ly or 0) * s.half[2]
    local lz = (q.lz or 0) * s.half[3]
    local ar, er = math.rad(q.a or 0), math.rad(q.e or 0)
    local dist = (q.m or (q.d or 1) * D)
    local cx = lx + math.sin(ar) * math.cos(er) * dist
    local cy = ly + math.sin(er) * dist + (q.h or 0)
    local cz = lz + math.cos(ar) * math.cos(er) * dist
    local sx, sy, sz = (q.sx or 0) * D, (q.sy or 0) * D, (q.sz or 0) * D
    cx, cy, cz = cx + sx, cy + sy, cz + sz
    local st = q.st or 0
    return cx, cy, cz, lx + sx * st, ly + sy * st, lz + sz * st
end

-- world camera and look point at progress p; frame f (the subject's now, or frozen for a tripod)
function VS:poseWorld(clip, p, f)
    local q = self:poseAt(clip, p)
    local cx, cy, cz, tx, ty, tz = self:poseLocal(clip, q)
    local wx, wy, wz = self:toWorld(f, cx, cy, cz)
    local ox, oy, oz = self:toWorld(f, tx, ty, tz)
    wy = math.max(wy, ground(wx, wz) + self.CLEARANCE)
    return { wx, wy, wz, ox, oy, oz }, q.fov or clip.fov
end


-- ------------------------------------------------------------------ in the way?
local function rayBoxEntry(ox, oy, oz, dx, dy, dz, lo, hi)
    local tmin, tmax = 0, math.huge
    local o, d = { ox, oy, oz }, { dx, dy, dz }
    for i = 1, 3 do
        if math.abs(d[i]) < 1e-9 then
            if o[i] < lo[i] or o[i] > hi[i] then return nil end
        else
            local t1, t2 = (lo[i] - o[i]) / d[i], (hi[i] - o[i]) / d[i]
            if t1 > t2 then t1, t2 = t2, t1 end
            tmin, tmax = math.max(tmin, t1), math.min(tmax, t2)
            if tmin > tmax then return nil end
        end
    end
    return tmin
end

function VS:rayMask()
    if self.mask == nil then
        local mask = 0
        if CollisionFlag ~= nil then
            for _, name in ipairs({ "DEFAULT", "TREE", "DYNAMIC_OBJECT", "VEHICLE", "BUILDING", "STATIC_OBJECT" }) do
                if type(CollisionFlag[name]) == "number" then mask = mask + CollisionFlag[name] end
            end
        end
        self.mask = mask > 0 and mask or nil
    end
    return self.mask
end

function VS:onViewRay(hitObjectId, x, y, z, distance)
    if hitObjectId ~= nil and hitObjectId ~= 0 then self.rayHit, self.rayDistance = hitObjectId, distance end
end

function VS:onSpotHit(hitObjectId)
    if hitObjectId ~= nil and hitObjectId ~= 0 and g_currentMission ~= nil and hitObjectId ~= g_currentMission.terrainRootNode then
        local obj = self:nodeObject(hitObjectId)
        if obj == nil or not (self.spotOwn or {})[obj] then self.spotHits = (self.spotHits or 0) + 1 end
    end
    return true
end

-- the object a hit node belongs to: the node itself, else its parents (a building's "LOD1" mesh)
function VS:nodeObject(id)
    if g_currentMission == nil or g_currentMission.getNodeObject == nil then return nil end
    local node = id
    for _ = 1, 12 do
        if node == nil or node == 0 then return nil end
        local ok, obj = pcall(g_currentMission.getNodeObject, g_currentMission, node)
        if ok and obj ~= nil then return obj end
        if getParent == nil then return nil end
        local pok, parent = pcall(getParent, node)
        node = pok and parent or nil
    end
    return nil
end

-- the hit node is part of a subject: one of its root or component nodes is above it
function VS:isOwnNode(node, subjects)
    if getParent == nil then return false end
    local roots = {}
    for o in pairs(subjects) do
        if type(o) == "table" then
            if o.rootNode ~= nil then roots[o.rootNode] = true end
            for _, c in ipairs(o.components or {}) do if c.node ~= nil then roots[c.node] = true end end
        end
    end
    local n = node
    for _ = 1, 40 do
        if n == nil or n == 0 then return false end
        if roots[n] then return true end
        local ok, parent = pcall(getParent, n)
        n = ok and parent or nil
    end
    return false
end

-- true, or false and what's in the way, for the camera at pos (world) looking at the subject
function VS:isClear(pos, corners, subjects)
    if not self.avoidObstacles or (raycastClosest == nil and overlapBox == nil) or #corners == 0 then return true end
    local lo, hi = { math.huge, math.huge, math.huge }, { -math.huge, -math.huge, -math.huge }
    for _, c in ipairs(corners) do
        for i = 1, 3 do lo[i], hi[i] = math.min(lo[i], c[i]), math.max(hi[i], c[i]) end
    end
    local bottom = lo[2] + math.min(0.5, (hi[2] - lo[2]) * 0.2)
    local terrain = g_currentMission ~= nil and g_currentMission.terrainRootNode or nil
    local cx, cy, cz = pos[1], pos[2], pos[3]
    for _, fx in ipairs({ 0, 0.5, 1 }) do
        for _, fy in ipairs({ 0, 0.5, 1 }) do
            for _, fz in ipairs({ 0, 0.5, 1 }) do
                local px = lo[1] + (hi[1] - lo[1]) * fx
                local py = bottom + (hi[2] - bottom) * fy
                local pz = lo[3] + (hi[3] - lo[3]) * fz
                local dx, dy, dz = px - cx, py - cy, pz - cz
                local len = math.sqrt(dx * dx + dy * dy + dz * dz)
                if len > 0.5 and raycastClosest ~= nil then
                    dx, dy, dz = dx / len, dy / len, dz / len
                    local reach = math.min(len, rayBoxEntry(cx, cy, cz, dx, dy, dz, lo, hi) or len) - 0.8
                    if reach > 0.5 then
                        self.rayHit, self.rayDistance = nil, nil
                        pcall(raycastClosest, cx, cy, cz, dx, dy, dz, reach, "onViewRay", self, self:rayMask())
                        if self.rayHit ~= nil and self.rayHit ~= terrain and not self:isOwnNode(self.rayHit, subjects) then
                            local obj = self:nodeObject(self.rayHit)
                            local root = obj ~= nil and obj.getRootVehicle ~= nil and obj:getRootVehicle() or nil
                            if not (obj ~= nil and (subjects[obj] or (root ~= nil and subjects[root]))) then
                                if obj == nil then
                                    local ok, nodeName = pcall(getName, self.rayHit)
                                    return false, string.format("'%s'", ok and tostring(nodeName) or "?")
                                end
                                return false, obj.getRootVehicle ~= nil and vehicleName(obj) or placeableName(obj)
                            end
                        end
                    end
                end
            end
        end
    end
    if overlapBox ~= nil and CollisionFlag ~= nil and type(CollisionFlag.TREE) == "number" then
        local tx, ty, tz = (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2, (lo[3] + hi[3]) / 2
        local dx, dy, dz = tx - cx, ty - cy, tz - cz
        local len = math.sqrt(dx * dx + dy * dy + dz * dz)
        if len > 1 then
            dx, dy, dz = dx / len, dy / len, dz / len
            local reach = math.min(len, rayBoxEntry(cx, cy, cz, dx, dy, dz, lo, hi) or len) - self.CROWN
            self.spotOwn = subjects
            local t = 1
            while t <= reach do
                self.spotHits = 0
                pcall(overlapBox, cx + dx * t, cy + dy * t, cz + dz * t, 0, 0, 0, self.CROWN, self.CROWN, self.CROWN,
                    "onSpotHit", self, CollisionFlag.TREE, true, true, true, false)
                if self.spotHits > 0 then return false, string.format("trees (%.0f m from the camera)", t) end
                t = t + self.CROWN
            end
        end
    end
    return true
end

-- how many of `samples` poses along the clip are blocked, and by what (the first)
function VS:blockedCount(clip, samples)
    local f = self:frameOf(clip.subject)
    local count, what = 0, nil
    for i = 0, samples - 1 do
        local p = samples > 1 and i / (samples - 1) or 0
        local pos = self:poseWorld(clip, p, f)
        local clear, block = self:isClear(pos, clip.subject.worldCorners, clip.subject.subjects)
        if not clear then
            count = count + 1
            what = what or block
        end
    end
    return count, what
end

-- Another way round when something is in the way: mirrored, higher, from further round. Not when
-- the angle was given (a=, angle=, side=) or the camera is our own pick anyway (tripod, own).
VS.DODGES = {
    { mirror = true }, { e = 12 }, { mirror = true, e = 12 }, { a = 60 }, { a = -60 }, { a = 120 }, { a = -120 }, { e = 24 },
}

function VS:dodge(clip)
    if not self.avoidObstacles or clip.fixedAngle or clip.own or clip.tripod then return end
    local samples = 7
    local base, what = self:blockedCount(clip, samples)
    if base == 0 then return end
    local best, bestCount, bestText = nil, base, nil
    local origFrom, origTo = copyTable(clip.from), copyTable(clip.to)
    for _, dz in ipairs(self.DODGES) do
        clip.from, clip.to = copyTable(origFrom), copyTable(origTo)
        for _, pose in ipairs({ clip.from, clip.to }) do
            if dz.mirror then
                if pose.a ~= nil then pose.a = -pose.a end
                if pose.sx ~= nil then pose.sx = -pose.sx end
                if pose.lx ~= nil then pose.lx = -pose.lx end
            end
            if dz.a ~= nil and pose.a ~= nil then pose.a = pose.a + dz.a end
            if dz.e ~= nil and pose.e ~= nil then pose.e = math.min(80, pose.e + dz.e) end
        end
        clip.D = self:baseDistance(clip)
        local n = self:blockedCount(clip, samples)
        if n < bestCount then
            best, bestCount = { from = clip.from, to = clip.to, D = clip.D }, n
            bestText = (dz.mirror and " mirrored" or "") .. (dz.a ~= nil and string.format(" %+d degrees round", dz.a) or "")
                .. (dz.e ~= nil and string.format(" %d degrees higher", dz.e) or "")
            if n == 0 then break end
        end
    end
    if best ~= nil then
        clip.from, clip.to, clip.D = best.from, best.to, best.D
        clip.blocked = bestCount
        log("Clip %d %s: %s in the way of %d/%d views, taken%s (%d blocked now)", clip.number, clip.shot, tostring(what),
            base, samples, bestText, bestCount)
    else
        clip.from, clip.to = origFrom, origTo
        clip.D = self:baseDistance(clip)
        clip.blocked = base
        log("Clip %d %s: %s in the way of %d/%d views from every side; taken anyway", clip.number, clip.shot,
            tostring(what), base, samples)
    end
end

-- one distance for the whole clip (the widest it needs), so an orbit doesn't breathe in and out
function VS:baseDistance(clip)
    local D = 0
    for i = 0, 8 do
        local q = self:poseAt(clip, i / 8)
        D = math.max(D, self:fitDistance(clip.subject, q.a or 0, q.e or 0, q.fov or clip.fov))
    end
    return D
end


-- ------------------------------------------------------------------ quiet: other mods' drawing
-- As Screenshot Studio: while a clip runs, the engine's 2D/debug drawing functions are swapped for
-- nothing where the game and every mod look them up (Courseplay's bar, AutoDrive's labels and lines,
-- the game's hint boxes); the START/END cards use the engine's own function, kept at load.
VS.QUIET_FUNCTIONS = { "renderText", "renderOverlay", "drawFilledRect", "drawDebugLine", "drawDebugPoint",
    "drawDebugTriangle", "drawDebugArrow", "drawDebugAreaRectangle", "renderText3D", "renderTextAtWorldPosition" }
VS.QUIET_AUTODRIVE = { "addLineTask", "addArrowTask", "addSmallSphereTask", "addMarkerTask", "addCrossTask", "addSphereTask" }
VS.muted = nil

local function nothing() end

local function field(t, key)
    local ok, v = pcall(function() return t[key] end)
    if ok then return v end
    return nil
end

local function findAutoDriveDrawing(g)
    local names = {}
    if g_modManager ~= nil and g_modManager.getActiveMods ~= nil then
        local ok, mods = pcall(g_modManager.getActiveMods, g_modManager)
        for _, mod in ipairs(ok and mods or {}) do
            if mod.modName ~= nil then table.insert(names, mod.modName) end
        end
    end
    table.insert(names, "FS25_AutoDrive")
    for _, name in ipairs(names) do
        local env = field(g, name)
        local dm = type(env) == "table" and field(env, "ADDrawingManager") or nil
        if type(dm) == "table" then return dm end
    end
    local dm = field(g, "ADDrawingManager")
    if type(dm) == "table" then return dm end
    return nil
end

-- keep (a mod's name): a clip with the HUD and menus. The game and that mod draw as always; only the
-- other mods' own drawing goes (Courseplay's label, other mods' alerts), by shadowing the functions in
-- their mod environments.
function VS:setQuiet(on, keep)
    if on then
        if self.muted ~= nil or not self.quietEnabled then return end
        local g = trueGlobals()
        local muted = {}
        local function mute(t, key)
            local f = field(t, key)
            if type(f) == "function" then
                table.insert(muted, { t, key, f, rawget(t, key) ~= nil })
                rawset(t, key, nothing)
            end
        end
        if keep ~= nil then
            local keepSet = {}
            for _, k in ipairs(type(keep) == "table" and keep or { keep }) do keepSet[k] = true end
            if g_modManager ~= nil and g_modManager.getActiveMods ~= nil then
                local ok, mods = pcall(g_modManager.getActiveMods, g_modManager)
                for _, mod in ipairs(ok and mods or {}) do
                    local name = mod.modName
                    local env = (name ~= nil and not keepSet[name] and name ~= self.MOD_NAME) and field(g, name) or nil
                    if type(env) == "table" and env ~= g and env ~= _G then
                        for _, fname in ipairs(self.QUIET_FUNCTIONS) do mute(env, fname) end
                    end
                end
            end
            local ad = not keepSet["FS25_AutoDrive"] and findAutoDriveDrawing(g) or nil
            if ad ~= nil then
                for _, name in ipairs(self.QUIET_AUTODRIVE) do mute(ad, name) end
            end
            self.muted = muted
            return
        end
        for _, name in ipairs(self.QUIET_FUNCTIONS) do mute(g, name) end
        local seen = { [g] = true }
        local function muteIn(t, depth)
            if type(t) ~= "table" or seen[t] or depth > 4 then return end
            seen[t] = true
            for _, name in ipairs(self.QUIET_FUNCTIONS) do
                if rawget(t, name) ~= nil then mute(t, name) end
            end
            local ok, mt = pcall(getmetatable, t)
            if ok and type(mt) == "table" and type(rawget(mt, "__index")) == "table" then muteIn(rawget(mt, "__index"), depth + 1) end
        end
        if g_modManager ~= nil and g_modManager.getActiveMods ~= nil then
            local ok, mods = pcall(g_modManager.getActiveMods, g_modManager)
            for _, mod in ipairs(ok and mods or {}) do
                local env = mod.modName ~= nil and field(g, mod.modName) or nil
                if type(env) == "table" and env ~= g then muteIn(env, 0) end
            end
        end
        muteIn(_G, 0)
        local ad = findAutoDriveDrawing(g)
        if ad ~= nil then
            for _, name in ipairs(self.QUIET_AUTODRIVE) do mute(ad, name) end
        end
        self.muted = muted
    elseif self.muted ~= nil then
        for i = #self.muted, 1, -1 do
            local m = self.muted[i]
            rawset(m[1], m[2], m[4] and m[3] or nil)
        end
        self.muted = nil
    end
end


-- ------------------------------------------------------------------ camera
function VS:getCamera()
    if self.camera == nil then
        self.camera = createCamera("videoStudioCamera", math.rad(self.FOV), 0.1, 10000)
        link(getRootNode(), self.camera)
        if setFastShadowUpdate ~= nil then setFastShadowUpdate(self.camera, true) end
        g_cameraManager:addCamera(self.camera, nil, false)
    end
    return self.camera
end

function VS:placeCamera(pos, fov)
    local cam = self:getCamera()
    local cx, cy, cz, tx, ty, tz = pos[1], pos[2], pos[3], pos[4], pos[5], pos[6]
    setWorldTranslation(cam, cx, cy, cz)
    if math.abs(cx - tx) + math.abs(cy - ty) + math.abs(cz - tz) > 1e-4 then
        setDirection(cam, cx - tx, cy - ty, cz - tz, 0, 1, 0)     -- cameras look along their -Z
    end
    if fov ~= nil and setFovY ~= nil and fov ~= self.cameraFov then
        setFovY(cam, math.rad(fov))
        self.cameraFov = fov
    end
    if g_cameraManager:getActiveCamera() ~= cam then g_cameraManager:setActiveCamera(cam) end
end


-- ------------------------------------------------------------------ START/END cards
-- the drawing functions, from the game's own table if the mod's environment didn't have them at load
function VS:engineDrawing()
    local g = trueGlobals()
    rawDrawRect = rawDrawRect or field(g, "drawFilledRect")
    rawRenderOverlay = rawRenderOverlay or field(g, "renderOverlay")
    rawSetOverlayColor = rawSetOverlayColor or field(g, "setOverlayColor")
    local create = createImageOverlay or field(g, "createImageOverlay")
    if self.overlay == nil and create ~= nil then
        local ok, id = pcall(create, self.MOD_DIR .. "textures/white.png")
        self.overlay = (ok and id ~= nil and id ~= 0) and id or nil
    end
    log("Cards: %s", self.overlay ~= nil and rawRenderOverlay ~= nil and "image overlay"
        or (rawDrawRect ~= nil and "drawFilledRect" or "NOTHING TO DRAW WITH"))
end

function VS:rect(x, y, w, h, r, g, b)
    if self.overlay ~= nil and rawRenderOverlay ~= nil and rawSetOverlayColor ~= nil then
        rawSetOverlayColor(self.overlay, r, g, b, 1)
        rawRenderOverlay(self.overlay, x, y, w, h)
    elseif rawDrawRect ~= nil then
        rawDrawRect(x, y, w, h, r, g, b, 1)
    end
end

function VS:drawMarker(from)
    local m = self.marker
    if m == nil then return end
    local c = self.MARK[m.kind]
    self:rect(0, 0, 1, 1, c[1], c[2], c[3])
    -- the clip number: 8 cells along the bottom quarter, most significant bit on the left
    for i = 0, 7 do
        local bit = math.floor(m.code / 2 ^ (7 - i)) % 2
        self:rect(i / 8, 0, 1 / 8, 0.25, bit, bit, bit)
    end
    if self.clip ~= nil then
        self.clip.cardDraws = (self.clip.cardDraws or 0) + 1
        self.clip.cardFrom = self.clip.cardFrom or from
    end
end

-- The cards must be the last thing drawn in a frame: mods like Mod Reveal draw their windows after the
-- mission (FSBaseMission.draw appended), over the GUI layer. So the mission's draw is wrapped once more
-- whenever someone else wrapped it after us: the cards come after everything.
function VS:ensureLateDraw()
    if FSBaseMission == nil or FSBaseMission.draw == nil or FSBaseMission.draw == self.lateDraw then return end
    local inner = FSBaseMission.draw
    self.lateDraw = function(...)
        inner(...)
        VS:drawMarker("late")
    end
    FSBaseMission.draw = self.lateDraw
end

function VS:setMarker(kind, clip)
    if kind == nil then
        self.marker = nil
    else
        self.marker = { kind = kind, code = ((clip.number - 1) % 255) + 1 }
    end
end


-- ------------------------------------------------------------------ options
-- "dur=10 deg=180 elev=8 dist=1.2 fov=35 side=right ease=linear a0=10 a1=90 hud=1"
function VS:parseOptions(words)
    local opts = {}
    for _, w in ipairs(words or {}) do
        local k, v = tostring(w):match("^([%a_]+%d?)=(.+)$")
        if k ~= nil then opts[k:lower()] = tonumber(v) or v end
    end
    return opts
end

-- A clip from a shot and its options, for the subject now
function VS:makeClip(shotId, opts)
    local def = self.SHOTS[shotId]
    if def == nil then return nil, "No shot called " .. tostring(shotId) end
    opts = opts or {}
    local clip = {
        shot = shotId, def = def, opts = opts,
        dur = tonumber(opts.dur) or def.dur,
        ease = self.EASES[opts.ease or def.ease or "sine"] and (opts.ease or def.ease or "sine") or "sine",
        from = copyTable(def.from or { a = 35, e = 12, d = 1 }),
        to = copyTable(def.to or {}),
        fov = tonumber(opts.fov) or self.fov or self.FOV,
        smooth = tonumber(opts.smooth) or def.smooth,
        own = def.own, hud = def.hud or tonumber(opts.hud) == 1, tripod = def.tripod,
        anchor = opts.anchor or def.anchor or "subject",
        text = def.text,
    }
    if opts.dur == 0 or opts.dur == "0" or opts.dur == "until" then
        -- until stopped (vsStop / Right Shift + 0); max= seconds for a long one filmed by hand (default 300)
        clip.dur, clip.untilStopped = math.min(tonumber(opts.max) or self.MAX_CLIP_S, 1800), true
    end
    local f, t = clip.from, clip.to
    -- angle: where it starts; deg: how far it turns (orbit, arcs); dir -1 the other way
    if opts.angle ~= nil then
        local shift = tonumber(opts.angle) - (f.a or 0)
        f.a = tonumber(opts.angle)
        if t.a ~= nil then t.a = t.a + shift end
        clip.fixedAngle = true
    end
    if opts.deg ~= nil then t.a = (f.a or 0) + tonumber(opts.deg) end
    if tonumber(opts.dir) == -1 and t.a ~= nil then t.a = (f.a or 0) - (t.a - (f.a or 0)) end
    if opts.side == "right" or opts.side == "left" then
        clip.fixedAngle = true
        local want = opts.side == "left" and 1 or -1     -- +x is the machine's left
        local sign = (f.a or 0) >= 0 and 1 or -1
        if sign ~= want then
            for _, pose in ipairs({ f, t }) do
                if pose.a ~= nil then pose.a = -pose.a end
                if pose.sx ~= nil then pose.sx = -pose.sx end
            end
        end
    end
    if opts.elev ~= nil then
        local shift = tonumber(opts.elev) - (f.e or 0)
        f.e = tonumber(opts.elev)
        if t.e ~= nil then t.e = t.e + shift end
    end
    if opts.dist ~= nil then
        local k = tonumber(opts.dist) or 1
        f.d = (f.d or 1) * k
        if t.d ~= nil then t.d = t.d * k end
    end
    if opts.height ~= nil then f.h = tonumber(opts.height) end
    -- raw pose keys: a0= start angle, a1= end angle, e0, e1, d0, d1, lz0, fov1, ...
    for k, v in pairs(opts) do
        local key, which = tostring(k):match("^(%a+)([01])$")
        if key ~= nil and tonumber(v) ~= nil then
            (which == "0" and f or t)[key] = tonumber(v)
            if key == "a" then clip.fixedAngle = true end
        end
    end
    if def.hours ~= nil then
        clip.hours = { tonumber(opts.from) or def.hours[1], tonumber(opts.to) or def.hours[2] }
    end
    if def.colors then
        clip.sweep = tonumber(opts.deg) or def.sweep
        clip.maxColors = tonumber(opts.max) or self.MAX_COLORS
        clip.config = opts.config
    end
    return clip
end


-- ------------------------------------------------------------------ the run of clips
function VS:isBusy()
    return self.run ~= nil
end

-- Queues clips: a list of "shot k=v ..." strings
function VS:queueClips(list)
    if g_currentMission == nil then return false, "No game" end
    local info = g_currentMission.missionDynamicInfo
    if info ~= nil and info.isMultiplayer then return false, "Single player only" end
    for _, text in ipairs(list) do
        local words = {}
        for w in tostring(text):gmatch("%S+") do table.insert(words, w) end
        local shot = table.remove(words, 1)
        if self.SHOTS[shot] == nil then return false, "No shot called " .. tostring(shot) .. ": vsShots lists them" end
        table.insert(self.queue, { shot = shot, opts = self:parseOptions(words), text = text })
    end
    if self.run == nil then self:startRun() end
    return true, string.format("%d clip(s) queued", #list)
end

function VS:startRun()
    local hud = g_currentMission.hud
    local subject = self:getSubject()
    local folder = safeName(self.forcedFolder or (subject ~= nil and subject.mod) or "misc")
    local dir = self:getBaseDir() .. folder .. "/"
    createFolder(getUserProfileAppPath() .. "modSettings/")
    createFolder(self:getBaseDir())
    createFolder(dir)
    self.run = {
        dir = dir, folder = folder, stamp = getDate("%Y%m%d_%H%M%S"),
        mod = subject ~= nil and subject.mod or folder, what = subject ~= nil and subject.what or nil,
        prevCamera = g_cameraManager:getActiveCamera(),
        hudWasVisible = hud ~= nil and (hud.getIsVisible == nil or hud:getIsVisible()),
        done = {}, count = 0,
    }
    log("Run started: clips go to %s (%s)", dir, tostring(self.run.what or "nothing framed yet"))
    self:nextClip()
end

function VS:setHud(visible)
    local hud = g_currentMission ~= nil and g_currentMission.hud or nil
    if hud ~= nil and hud.setIsVisible ~= nil then hud:setIsVisible(visible) end
end

-- help=0 on a clip: the game's F1 help box hidden while it rolls (other mods' keys in it are clutter in a
-- video about one mod); it comes back after the clip as it was
function VS:setInputHelp(visible)
    local hud = g_currentMission ~= nil and g_currentMission.hud or nil
    if hud == nil then return false end
    if hud.setInputHelpVisible ~= nil then
        return pcall(hud.setInputHelpVisible, hud, visible) and "setInputHelpVisible"
    end
    local ih = hud.inputHelp
    if ih ~= nil and ih.setVisible ~= nil then
        return pcall(ih.setVisible, ih, visible) and "inputHelp:setVisible"
    end
    return false
end

function VS:setPlayerHidden(hidden)
    local player = g_localPlayer
    local gc = player ~= nil and player.graphicsComponent or nil
    if gc == nil or gc.setModelVisibility == nil then return end
    if hidden and not self.playerHidden and self:getSeatVehicle() == nil and self.hidePlayer then
        pcall(gc.setModelVisibility, gc, false)
        self.playerHidden = true
    elseif not hidden and self.playerHidden then
        pcall(gc.setModelVisibility, gc, true)
        self.playerHidden = false
    end
end

function VS:nextClip()
    local r = self.run
    if r == nil then return end
    local item = table.remove(self.queue, 1)
    if item == nil then
        self:finishRun()
        return
    end
    if item.color ~= nil then return self:startColorClip(item) end
    local subject = self:getSubject()
    local def = self.SHOTS[item.shot]
    if subject == nil and not def.own then
        log("Clip %s: nothing to film (sit in a vehicle, stand next to one, or vsTarget it): skipped", item.text)
        notify("Video Studio: nothing to film nearby")
        return self:nextClip()
    end
    if def.colors then return self:startColors(item, subject) end
    self:startClip(item, subject)
end

function VS:startClip(item, subject, extra)
    local clip, err = self:makeClip(item.shot, item.opts)
    if clip == nil then
        log("%s", err)
        return self:nextClip()
    end
    self.clipNumber = self.clipNumber + 1
    clip.number, clip.text, clip.subject = self.clipNumber, item.text, subject
    for k, v in pairs(extra or {}) do clip[k] = v end
    self.clip = clip
    if clip.color == nil then
        self:deleteCopies()
        self:showOriginals(true)
    end
    if not clip.own and self.sunSide and subject.kind == "building" and not clip.fixedAngle then
        local sunYaw = self:sunYaw()
        if sunYaw ~= nil then
            local f = self:frameOf(subject)
            local delta = math.deg(sunYaw - math.atan2(f.fx, f.fz)) - 35
            delta = (delta + 180) % 360 - 180
            for _, pose in ipairs({ clip.from, clip.to }) do
                if pose.a ~= nil then pose.a = pose.a + delta end
            end
        end
    end
    if not clip.own then
        clip.D = clip.D or self:baseDistance(clip)
        self:dodge(clip)
        if clip.tripod then self:setupTripod(clip) end
        clip.frame0 = self:frameOf(subject)
    elseif self.run.prevCamera ~= nil and g_cameraManager:getActiveCamera() ~= self.run.prevCamera then
        g_cameraManager:setActiveCamera(self.run.prevCamera)     -- the player's own camera again
    end
    if clip.hours ~= nil then
        local env = self:getEnv()
        if env ~= nil then clip.timeBefore = { env.currentMonotonicDay, env.currentDay, env.dayTime, env.daysPerPeriod } end
    end
    self:setHud(clip.hud == true)
    if tonumber(clip.opts.help) == 0 and not self.helpHidden then
        local how = self:setInputHelp(false)
        self.helpHidden = how and true or nil
        log("F1 help box %s", how and ("hidden (" .. how .. ")") or "can't be hidden here")
    end
    self:setQuiet(false)
    if not clip.hud then
        self:setQuiet(true)
    elseif self.forcedFolder ~= nil then
        -- menus: only the mod being filmed (vsFolder), the game, and keep=A+B (a HUD the mod sits on)
        local keep = { self.forcedFolder }
        for k in tostring(clip.opts.keep or ""):gmatch("[^+,]+") do table.insert(keep, k) end
        self:setQuiet(true, keep)
    end
    self:setPlayerHidden(not clip.own)
    -- the START card goes up at once: the camera jump and the streaming happen under it
    self:ensureLateDraw()
    self:setMarker("start", clip)
    if not clip.own then self:applyPose(clip, 0, 0) end
    clip.state = clip.loading and "loading" or "settle"
    clip.stateAt = now()
    clip.settleMs = (self.run.count == 0 and self.SETTLE_FIRST_MS or self.SETTLE_MS)
    if clip.own then clip.settleMs = math.min(clip.settleMs, 800) end
    if clip.colorIndex ~= nil and clip.colorIndex > 1 then clip.settleMs = self.SETTLE_MS end
    local light = self.light ~= nil and self.LIGHTS[self.light].id or "game"
    log("Clip %d %s (%s): %.1f s, %s, light %s%s", clip.number, clip.shot, clip.text, clip.dur,
        subject ~= nil and subject.what or "own camera", light, clip.color ~= nil and (", color " .. clip.color) or "")
end

-- a drive-past: the camera on the ground ahead of the machine and to its side, where it will pass
function VS:setupTripod(clip)
    local s = clip.subject
    local speed = 0
    if s.vehicle ~= nil and s.vehicle.getLastSpeed ~= nil then
        local ok, v = pcall(s.vehicle.getLastSpeed, s.vehicle)
        speed = ok and tonumber(v) or 0     -- km/h
    end
    local ahead = tonumber(clip.opts.ahead) or math.max(s.half[3] * 2.5, speed / 3.6 * clip.dur * 0.45)
    local side = tonumber(clip.opts.sidem) or math.max(5, s.half[1] * 2.2)
    if clip.opts.side == "right" then side = -side end
    clip.from = { m = 0.001, sx = side / clip.D, sy = (1.4 - s.half[2]) / clip.D, sz = ahead / clip.D, st = 0 }
    clip.to = {}
    clip.anchor, clip.track = "world", true
end

-- the camera for progress p; dt (ms) for the smoothing
function VS:applyPose(clip, p, dt)
    local f = (clip.anchor == "world") and clip.frame0 or self:frameOf(clip.subject)
    local pos, fov = self:poseWorld(clip, p, f)
    if clip.track then
        -- a tripod: stays where it is and looks at the machine now
        local live = self:frameOf(clip.subject)
        pos[4], pos[5], pos[6] = live.cx, live.cy, live.cz
    end
    -- a camera operator's lag: the camera eases towards where it should be (a second call in the
    -- same frame, from the GUI update, moves nothing)
    if clip.smooth ~= nil and clip.smooth > 0 then
        if clip.smoothed == nil then
            clip.smoothed = { unpack(pos) }
        elseif dt > 0 then
            local k = 1 - math.exp(-(dt / 1000) / clip.smooth)
            for i = 1, 6 do clip.smoothed[i] = clip.smoothed[i] + (pos[i] - clip.smoothed[i]) * k end
        end
        pos = { unpack(clip.smoothed) }
        pos[2] = math.max(pos[2], ground(pos[1], pos[3]) + self.CLEARANCE)
    end
    self:placeCamera(pos, fov)
end

function VS:tick()
    local clip = self.clip
    if clip == nil then return end
    local t = now()
    local elapsed = t - clip.stateAt
    local dt = clip.lastTick ~= nil and (t - clip.lastTick) or 0
    clip.lastTick = t
    if clip.state == "loading" then
        if elapsed >= self.LOAD_TIMEOUT_MS then
            log("Clip %d: the color copy didn't load in %d s, skipped", clip.number, self.LOAD_TIMEOUT_MS / 1000)
            self:endClip(false)
        end
        return
    end
    if clip.state == "settle" then
        if not clip.own then self:applyPose(clip, 0, dt) end
        -- the game puts a fresh copy back to its start pose a frame or two after loading: folded or
        -- unfolded like the original again, every frame until the clip rolls
        self:holdCopies()
        if elapsed >= clip.settleMs then
            clip.state, clip.stateAt, clip.rollStart = "roll", t, t
            self:setMarker(nil)
        end
    elseif clip.state == "roll" then
        if clip.color ~= nil then self:holdCopies() end
        self:clipKeys(clip, elapsed / 1000)
        local raw = math.min(1, elapsed / (clip.dur * 1000))
        local p = self.EASES[clip.ease](raw)
        if not clip.own then self:applyPose(clip, p, dt) end
        if clip.hours ~= nil then self:timelapse(clip, raw) end
        if raw >= 1 or clip.stopNow then
            clip.rolled = (t - clip.rollStart) / 1000
            clip.state, clip.stateAt = "end", t
            self:setMarker("end", clip)
        end
    elseif clip.state == "end" then
        if elapsed >= self.END_MS then self:endClip(true) end
    end
end

-- Keys the runner types during the clip (a menu opening on camera): keys=lalt+i,pause,right at=1.5;
-- more with keys2= at2=, keys3= at3=. "," between key words (no spaces in an option). A console command
-- during the clip: run=vsMenu:ShopMenu at=1 (":" between its words).
function VS:clipKeys(clip, seconds)
    clip.keysSent = clip.keysSent or {}
    for _, n in ipairs({ "", "2", "3", "4", "5" }) do
        local spec = clip.opts["keys" .. n]
        local at = tonumber(clip.opts["at" .. n]) or 0.5
        if spec ~= nil and not clip.keysSent["k" .. n] and seconds >= at then
            clip.keysSent["k" .. n] = true
            log("keys: %s", tostring(spec):gsub(",", " "))
        end
        local cmd = clip.opts["run" .. n]
        if cmd ~= nil and not clip.keysSent["r" .. n] and seconds >= at then
            clip.keysSent["r" .. n] = true
            local _, result = self:runStep((tostring(cmd):gsub(":", " ")))
            log("Clip %d: %s -> %s", clip.number, tostring(cmd), tostring(result))
        end
    end
end

function VS:timelapse(clip, raw)
    local t = now()
    if clip.lapseAt ~= nil and t - clip.lapseAt < 40 then return end
    clip.lapseAt = t
    local env = self:getEnv()
    if env == nil then return end
    local h = lerp(clip.hours[1], clip.hours[2], raw)
    self:setTime(env, env.currentMonotonicDay, env.currentDay, math.floor(h * 3600000), env.daysPerPeriod)
end

function VS:endClip(ok)
    local clip, r = self.clip, self.run
    self.clip = nil
    if ok and r ~= nil then
        r.count = r.count + 1
        table.insert(r.done, {
            number = clip.number, code = ((clip.number - 1) % 255) + 1, shot = clip.shot, text = clip.text,
            duration = clip.rolled or clip.dur, what = clip.subject ~= nil and clip.subject.what or "own camera",
            mod = clip.subject ~= nil and clip.subject.mod or r.mod,
            light = self.light ~= nil and self.LIGHTS[self.light].id or "game",
            hour = self:getHour(), color = clip.color, colorIndex = clip.colorIndex, colorCount = clip.colorCount,
            fov = clip.fov, blocked = clip.blocked or 0, hud = clip.hud == true, own = clip.own == true,
            description = clip.def.text,
        })
        log("Clip %d done: %.2f s (its cards drawn %d times, from %s)", clip.number, clip.rolled or 0,
            clip.cardDraws or 0, tostring(clip.cardFrom or "nowhere"))
    end
    if clip.timeBefore ~= nil then          -- a time-lapse: the clock back where it was
        local env, g = self:getEnv(), clip.timeBefore
        if env ~= nil then self:setTime(env, g[1], g[2], g[3], g[4]) end
    end
    self:nextClip()
end

function VS:finishRun()
    local r = self.run
    if r == nil then return end
    self:setMarker(nil)
    self:deleteCopies()
    self:showOriginals(true)
    self:setQuiet(false)
    self:setPlayerHidden(false)
    if self.helpHidden then
        self:setInputHelp(true)
        self.helpHidden = nil
    end
    if r.prevCamera ~= nil and g_cameraManager:getActiveCamera() ~= r.prevCamera then
        g_cameraManager:setActiveCamera(r.prevCamera)
    end
    self:setHud(r.hudWasVisible)
    self.run, self.clip, self.colorJob = nil, nil, nil
    self:writeManifest(r)
    if self.autorun ~= nil then self.autorun.clips = self.autorun.clips + r.count end
    log("Run done: %d clip(s), list in %s_clips_%s.xml", r.count, r.dir, r.stamp)
    -- not while filming by script: it would sit in the next clip's picture
    if self.autorun == nil then notify(string.format("Video Studio: %d clip(s) filmed", r.count)) end
end

function VS:stop()
    self.queue = {}
    if self.clip == nil then return "Nothing running" end
    if self.clip.state == "roll" then
        self.clip.stopNow = true
        return "Stopping: the clip ends now"
    end
    -- not rolling yet: nothing worth keeping
    self.clip = nil
    self:finishRun()
    return "Stopped"
end

function VS:getHour()
    local env = self:getEnv()
    if env == nil or env.dayTime == nil then return nil end
    return env.dayTime / 3600000
end

function VS:writeManifest(r)
    if #r.done == 0 then return end
    local path = string.format("%s_clips_%s.xml", r.dir, r.stamp)
    local xml = createXMLFile("vsClips", path, "clips")
    if xml == nil or xml == 0 then return end
    setXMLString(xml, "clips#mod", tostring(r.mod or ""))
    setXMLString(xml, "clips#what", tostring(r.what or ""))
    setXMLString(xml, "clips#stamp", r.stamp)
    setXMLString(xml, "clips#version", tostring(self.version or ""))
    local info = g_currentMission ~= nil and g_currentMission.missionInfo or nil
    if info ~= nil then setXMLString(xml, "clips#map", tostring(info.mapTitle or info.mapId or "")) end
    for i, c in ipairs(r.done) do
        local key = string.format("clips.clip(%d)", i - 1)
        setXMLString(xml, key .. "#n", tostring(c.number))
        setXMLString(xml, key .. "#code", tostring(c.code))
        setXMLString(xml, key .. "#shot", c.shot)
        setXMLString(xml, key .. "#args", tostring(c.text))
        setXMLString(xml, key .. "#duration", string.format("%.3f", c.duration))
        setXMLString(xml, key .. "#what", tostring(c.what))
        setXMLString(xml, key .. "#mod", tostring(c.mod))
        setXMLString(xml, key .. "#light", tostring(c.light))
        if c.hour ~= nil then setXMLString(xml, key .. "#hour", string.format("%.2f", c.hour)) end
        if c.color ~= nil then
            setXMLString(xml, key .. "#color", tostring(c.color))
            setXMLString(xml, key .. "#colorIndex", tostring(c.colorIndex))
            setXMLString(xml, key .. "#colorCount", tostring(c.colorCount))
        end
        setXMLString(xml, key .. "#fov", string.format("%.1f", c.fov or self.FOV))
        setXMLString(xml, key .. "#blocked", tostring(c.blocked))
        setXMLString(xml, key .. "#hud", c.hud and "true" or "false")
        setXMLString(xml, key .. "#description", tostring(c.description or ""))
    end
    saveXMLFile(xml)
    delete(xml)
end


-- ------------------------------------------------------------------ every color
-- Copies of the vehicle in each color, loaded the way the shop does it (as Screenshot Studio),
-- without physics, where the vehicle stands, while it is hidden. One short clip per color; the camera
-- carries on round between them, so the cut from one to the next looks like the paint changing.
function VS:configTitle(storeItem, name)
    local path = storeItem ~= nil and storeItem.xmlFilename or nil
    if path == nil then return "" end
    self.titleCache = self.titleCache or {}
    local key = path .. "|" .. name
    if self.titleCache[key] ~= nil then return self.titleCache[key] end
    local title = ""
    local ok, xml = pcall(loadXMLFile, "vsVehicle", path)
    if ok and xml ~= nil and xml ~= 0 then
        title = getXMLString(xml, "vehicle." .. name .. "Configurations#title") or ""
        delete(xml)
    end
    local text = title
    if title:sub(1, 6) == "$l10n_" and g_i18n ~= nil and g_i18n.getText ~= nil then
        local tok, translated = pcall(g_i18n.getText, g_i18n, title:sub(7), storeItem.customEnvironment)
        if tok and translated ~= nil then text = title .. " " .. tostring(translated) end
    end
    self.titleCache[key] = text:lower()
    return self.titleCache[key]
end

local function titleHas(title, words)
    for _, w in ipairs(words) do
        if title:find(w, 1, true) then return true end
    end
    return false
end

function VS:pickColorConfig(storeItem, name)
    local configs = storeItem.configurations or {}
    local function choices(n)
        local count = 0
        for _, item in ipairs(configs[n] or {}) do
            if item.isSelectable ~= false then count = count + 1 end
        end
        return count
    end
    if name ~= nil and name ~= "" then return configs[name] ~= nil and name or nil end
    local candidates = {}
    for _, n in ipairs(self.COLOR_CONFIGS) do
        if choices(n) > 1 then table.insert(candidates, n) end
    end
    if #candidates > 0 then
        local fallback
        for _, n in ipairs(candidates) do
            local title = self:configTitle(storeItem, n)
            if titleHas(title, self.BODY_WORDS) then return n end
            if fallback == nil and not titleHas(title, self.NOT_BODY_WORDS) then fallback = n end
        end
        return fallback or candidates[1]
    end
    local names = {}
    for n in pairs(configs) do table.insert(names, n) end
    table.sort(names)
    for _, n in ipairs(names) do
        if n:lower():find("color") ~= nil and choices(n) > 1 then return n end
    end
    return nil
end

function VS:startColors(item, subject)
    local v = subject.vehicle
    if v ~= nil and subject.group ~= nil and subject.group.subject ~= nil then v = subject.group.subject end
    local storeItem = v ~= nil and v.configFileName ~= nil and g_storeManager ~= nil
        and g_storeManager:getItemByXMLFilename(v.configFileName) or nil
    local opts = self:parseOptions({})
    for k, val in pairs(item.opts) do opts[k] = val end
    local name = storeItem ~= nil and VehicleLoadingData ~= nil and self:pickColorConfig(storeItem, opts.config) or nil
    if name == nil then
        log("Colors: %s has no color option%s: skipped", subject.what, opts.config and (" called " .. opts.config) or "")
        return self:nextClip()
    end
    local all = {}
    for i, it in ipairs(storeItem.configurations[name]) do
        if it.isSelectable ~= false then
            table.insert(all, { id = it.index or i, label = it.name ~= nil and tostring(it.name) or (name .. " " .. i) })
        end
    end
    -- at most maxColors, spread over the list (the first and the last in)
    local maxColors = tonumber(opts.max) or self.MAX_COLORS
    local pick = {}
    if #all <= maxColors then
        pick = all
    else
        for k = 0, maxColors - 1 do
            table.insert(pick, all[1 + math.floor(k * (#all - 1) / (maxColors - 1) + 0.5)])
        end
    end
    -- what's hitched to it changes color with it, matched by name, else by place in the list
    local extras = {}
    for _, o in ipairs(subject.group ~= nil and subject.group.list or {}) do
        if o ~= v and o.configFileName ~= nil then
            local it = g_storeManager:getItemByXMLFilename(o.configFileName)
            local cfg = it ~= nil and ((it.configurations or {})[name] ~= nil and #it.configurations[name] > 1 and name
                or self:pickColorConfig(it)) or nil
            if cfg ~= nil then table.insert(extras, { vehicle = o, storeItem = it, config = cfg }) end
        end
    end
    local sweep = tonumber(opts.deg) or self.SHOTS.colors.sweep
    local per = tonumber(opts.dur) or self.SHOTS.colors.dur
    local a0 = tonumber(opts.angle) or self.SHOTS.colors.from.a
    -- one queued clip per color, in front of what was queued after it; the camera carries on round
    -- at one distance for all of them (the widest the whole sweep needs), so the cuts don't jump
    local list = {}
    local probe = self:makeClip("colors", { a0 = a0, a1 = a0 + sweep, fov = opts.fov })
    probe.subject = subject
    local D = self:baseDistance(probe)
    for k, c in ipairs(pick) do
        local step = sweep / #pick
        local o = {}
        for key, val in pairs(opts) do o[key] = val end
        o.a0, o.a1, o.dur = a0 + (k - 1) * step, a0 + k * step, per
        o.ease = "linear"
        table.insert(list, { shot = "colors", opts = o, text = item.text, color = c, k = k })
    end
    self.colorJob = { vehicle = v, storeItem = storeItem, config = name, extras = extras, count = #pick, subject = subject, D = D }
    log("Colors of %s: %d of %d x %s, %.1f s each, the camera turning %d degrees", subject.what, #pick, #all, name, per, sweep)
    for k = #list, 1, -1 do table.insert(self.queue, 1, list[k]) end
    return self:nextClip()
end

-- a queued color clip: its copies first (under the START card), then the clip
function VS:startColorClip(item)
    local job = self.colorJob
    if job == nil or isGone(job.vehicle) then return self:nextClip() end
    self:deleteCopies()
    self:startClip(item, job.subject, { color = item.color.label, colorIndex = item.k, colorCount = job.count,
        loading = true, D = job.D })
    self:hideOriginals(job)
    if self.clip ~= nil and self.clip.color ~= nil then self:loadCopies(self.clip, job, item.color) end
end

function VS:hideOriginals(job)
    if self.hidden ~= nil then return end
    self.hidden = {}
    local list = { job.vehicle }
    for _, e in ipairs(job.extras) do table.insert(list, e.vehicle) end
    for _, v in ipairs(list) do
        for _, c in ipairs(v.components or {}) do
            if c.node ~= nil and (getVisibility == nil or getVisibility(c.node)) then
                setVisibility(c.node, false)
                table.insert(self.hidden, c.node)
            end
        end
    end
end

function VS:showOriginals(really)
    if not really or self.hidden == nil then return end
    for _, node in ipairs(self.hidden) do setVisibility(node, true) end
    self.hidden = nil
end

function VS:loadCopies(clip, job, color)
    local loads = { { vehicle = job.vehicle, storeItem = job.storeItem, config = job.config, id = color.id, main = true } }
    for _, e in ipairs(job.extras) do
        local list = e.storeItem.configurations[e.config]
        local id
        for j, it in ipairs(list) do
            if it.name ~= nil and tostring(it.name):lower() == color.label:lower() then id = it.index or j end
        end
        if id == nil and list[clip.colorIndex] ~= nil then id = list[clip.colorIndex].index or clip.colorIndex end
        if id ~= nil then table.insert(loads, { vehicle = e.vehicle, storeItem = e.storeItem, config = e.config, id = id }) end
    end
    clip.pending, clip.mainFailed = #loads, false
    self.copies = {}
    for _, l in ipairs(loads) do
        local v = l.vehicle
        local configs = {}
        for k, id in pairs(v.configurations or {}) do configs[k] = id end
        configs[l.config] = l.id
        local x, y, z = getWorldTranslation(v.rootNode)
        local rx, ry, rz = getWorldRotation(v.rootNode)
        local data = VehicleLoadingData.new()
        data:setStoreItem(l.storeItem)
        data:setConfigurations(configs)
        data:setPosition(x, y, z)
        data:setRotation(rx, ry, rz)
        if data.setIgnoreShopOffset ~= nil then data:setIgnoreShopOffset(true) end
        data:setAddToPhysics(false)
        data:setIsSaved(false)
        if v.getOwnerFarmId ~= nil then data:setOwnerFarmId(v:getOwnerFarmId()) end
        local ok, err = pcall(data.load, data, self.onCopyLoaded, self, { clip = clip, like = v, main = l.main })
        if not ok then
            log("Color %s: loading %s failed: %s", color.label, vehicleName(v), tostring(err))
            self:copyDone(clip, l.main)
        end
    end
end

function VS:copyDone(clip, failedMain)
    if failedMain then clip.mainFailed = true end
    clip.pending = clip.pending - 1
    if clip.pending > 0 or self.clip ~= clip then return end
    if clip.mainFailed then
        log("Color %s: no copy, skipped", tostring(clip.color))
        self.clip = nil
        self:nextClip()
    else
        clip.state, clip.stateAt = "settle", now()
    end
end

function VS:onCopyLoaded(vehicles, loadingState, args)
    local clip = args.clip
    if self.clip ~= clip then
        for _, v in ipairs(vehicles or {}) do pcall(v.delete, v) end
        return
    end
    local okState = VehicleLoadingState == nil or loadingState == VehicleLoadingState.OK
    if not okState or vehicles == nil or vehicles[1] == nil then
        log("Color %s: the copy of %s didn't load (%s)", tostring(clip.color), vehicleName(args.like), tostring(loadingState))
        for _, v in ipairs(vehicles or {}) do pcall(v.delete, v) end
        self:copyDone(clip, args.main)
        return
    end
    for _, v in ipairs(vehicles) do table.insert(self.copies, v) end
    -- colors fold=alt: open, closed, open ... (a copy loads closed; the open ones match the original)
    vehicles[1].vsClosed = tostring(clip.opts.fold) == "alt" and (clip.colorIndex or 1) % 2 == 0 or nil
    self:placeLikeOriginal(vehicles[1], args.like, vehicles[1].vsClosed)
    vehicles[1].vsLike = args.like
    if not vehicles[1].vsClosed then self:mirrorFold(vehicles[1], args.like) end
    self:copyDone(clip, false)
end

-- a copy loads folded: folded or unfolded like the original at once (each folding animation at the
-- original's time), so an unfolded machine stays unfolded through its colors
function VS:mirrorFold(copy, like)
    local a, b = like ~= nil and like.spec_foldable or nil, copy ~= nil and copy.spec_foldable or nil
    if a == nil or b == nil or copy.setAnimationTime == nil or like.getAnimationTime == nil then return end
    for i, part in ipairs(a.foldingParts or {}) do
        local other = (b.foldingParts or {})[i]
        if part.animationName ~= nil and other ~= nil then
            local ok, t = pcall(like.getAnimationTime, like, part.animationName)
            if ok and t ~= nil then pcall(copy.setAnimationTime, copy, other.animationName or part.animationName, t, true) end
        end
    end
    b.foldAnimTime, b.foldMoveDirection = a.foldAnimTime, a.foldMoveDirection
    if not copy.vsFoldLogged and a.foldAnimTime ~= nil then
        copy.vsFoldLogged = true
        log("Copy of %s folded like the original (fold time %.2f)", vehicleName(like), a.foldAnimTime)
    end
end

-- the open copies of a color clip: unfolded and every part where the original's is, every frame (unfolded
-- wings hang on joints and drift back by themselves: copies held only until the clip rolled ended half folded)
function VS:holdCopies()
    for _, c in ipairs(self.copies or {}) do
        if c.vsLike ~= nil and not c.vsClosed and not isGone(c.vsLike) then
            self:mirrorFold(c, c.vsLike)
            self:placeLikeOriginal(c, c.vsLike)
        end
    end
end

function VS:placeLikeOriginal(copy, v, rootOnly)
    if copy.setAbsolutePosition == nil then return end
    local x, y, z = getWorldTranslation(v.rootNode)
    local rx, ry, rz = getWorldRotation(v.rootNode)
    local positions
    -- every part (component) where the original's is; rootOnly: only the machine's spot, its parts as they
    -- loaded (a copy that stays folded while the original is unfolded)
    if not rootOnly and copy.components ~= nil and v.components ~= nil and #copy.components == #v.components then
        positions = {}
        for i, c in ipairs(v.components) do
            positions[i] = { { getWorldTranslation(c.node) }, { getWorldRotation(c.node) } }
        end
    end
    pcall(copy.setAbsolutePosition, copy, x, y, z, rx, ry, rz, positions)
end

function VS:deleteCopies()
    for _, v in ipairs(self.copies or {}) do
        local ok, err = pcall(v.delete, v)
        if not ok then log("Deleting the copy: %s", tostring(err)) end
    end
    self.copies = nil
end


-- ------------------------------------------------------------------ light and weather
function VS:getEnv()
    return g_currentMission ~= nil and g_currentMission.environment or nil
end

function VS:setTime(env, md, day, dayTime, dpp)
    local ok, err = pcall(env.setEnvironmentTime, env, md, day, dayTime, dpp, false)
    if ok and env.lighting ~= nil and env.lighting.update ~= nil then pcall(env.lighting.update, env.lighting, 1, true) end
    return ok, err
end

function VS:setWeather(env, typeName)
    local w = env.weather
    if w == nil or w.consoleCommandWeatherSet == nil then return false end
    if WeatherType ~= nil and WeatherType[typeName] == nil then
        log("Weather type %s doesn't exist here, keeping the weather", typeName)
        return false
    end
    local ok, msg = pcall(w.consoleCommandWeatherSet, w, typeName)
    if msg ~= nil then log("Weather %s: %s", typeName, tostring(msg)) end
    return ok
end

function VS:setMist(env, on)
    local w = env.weather
    local updater = w ~= nil and w.fogUpdater or nil
    if updater == nil or updater.setTargetFog == nil then return false end
    if on then
        local template = w.seasonToFog ~= nil and w.seasonToFog[env.currentSeason] or nil
        if template == nil or template.createFromTemplate == nil then return false end
        local ok, fog = pcall(template.createFromTemplate, template)
        if not ok or fog == nil then return false end
        for k, value in pairs(self.MIST) do fog[k] = value end
        fog.groundFogStartDayTimeMinutes, fog.groundFogEndDayTimeMinutes = 0, 1439
        fog.groundFogWeatherTypes = fog.groundFogWeatherTypes or {}
        if WeatherType ~= nil and WeatherType.SUN ~= nil then fog.groundFogWeatherTypes[WeatherType.SUN] = true end
        if self.lightSaved ~= nil and not self.lightSaved.fogSaved then
            self.lightSaved.fog, self.lightSaved.fogSaved = updater.targetFog, true
        end
        return (pcall(updater.setTargetFog, updater, fog, 1000))
    elseif self.lightSaved ~= nil and self.lightSaved.fogSaved then
        pcall(updater.setTargetFog, updater, self.lightSaved.fog, 1000)
        self.lightSaved.fog, self.lightSaved.fogSaved = nil, false
    end
    return true
end

function VS:setLight(i, hour)
    local env = self:getEnv()
    if env == nil then return "No environment" end
    local preset = self.LIGHTS[i]
    if self.lightSaved == nil then
        self.lightSaved = { env.currentMonotonicDay, env.currentDay, env.dayTime, env.daysPerPeriod }
    end
    local h = tonumber(hour) or preset.hour
    local ok, err = self:setTime(env, env.currentMonotonicDay, env.currentDay, math.floor(h * 3600000), env.daysPerPeriod)
    if not ok then return "Light failed: " .. tostring(err) end
    self.light = i
    self:setWeather(env, preset.weather)
    local mist = self:setMist(env, preset.fog == true)
    -- night turns the lights on; the next preset turns off only what night turned on
    if preset.lights then
        self:setVehicleLights("on")
        self.lightsByPreset = true
    elseif self.lightsByPreset then
        self:setVehicleLights("off")
        self.lightsByPreset = false
    end
    local msg = string.format("Light %d/%d: %s, %02d:%02d%s", i, #self.LIGHTS, preset.text, math.floor(h),
        math.floor((h % 1) * 60 + 0.5), (preset.fog and not mist) and " (no fog in this game)" or "")
    notify("Video Studio: " .. msg)
    return msg
end

function VS:restoreLight()
    local env = self:getEnv()
    if env == nil or self.lightSaved == nil then
        self.light = nil
        return "Light: the game's own"
    end
    local g = self.lightSaved
    self:setMist(env, false)
    local ok, err = self:setTime(env, g[1], g[2], g[3], g[4])
    self.light, self.lightSaved = nil, nil
    if self.lightsByPreset then
        self:setVehicleLights("off")
        self.lightsByPreset = false
    end
    return ok and "Time is back to where it was (the weather stays)" or ("Restore failed: " .. tostring(err))
end

function VS:nextLight()
    local i = (self.light or 0) + 1
    if i > #self.LIGHTS then return self:restoreLight() end
    return self:setLight(i)
end

function VS:getLightIndex(id)
    for i, preset in ipairs(self.LIGHTS) do
        if preset.id == id then return i end
    end
    return nil
end

-- the subject's lights: on (headlights and work lights), beacon, all, off
VS.LIGHTS_MASK = 1 + 2 + 4 + 8
function VS:setVehicleLights(mode)
    local s = self:getSubject()
    local list = s ~= nil and s.group ~= nil and s.group.list or {}
    local n = 0
    for _, v in ipairs(list) do
        if v.setLightsTypesMask ~= nil then
            local mask = (mode == "on" or mode == "all") and self.LIGHTS_MASK or 0
            if pcall(v.setLightsTypesMask, v, mask, true, true) then n = n + 1 end
        end
        if v.setBeaconLightsVisibility ~= nil then
            pcall(v.setBeaconLightsVisibility, v, mode == "beacon" or mode == "all", true, true)
        end
    end
    return string.format("Vehicle lights %s (%d vehicle(s))", mode, n)
end



-- ------------------------------------------------------------------ the sun
-- Where the sun is on the flat (radians, world, like a yaw) and how high, from the game's sun light
-- (a light shines along its -Z: its +Z points back at the sun). Low golden-hour sun behind the camera
-- lights the machine; in front of it, the machine is a silhouette.
function VS:sunYaw()
    local env = self:getEnv()
    local lighting = env ~= nil and env.lighting or nil
    local ids = {}
    for _, t in ipairs({ lighting or {}, env or {} }) do
        for _, k in ipairs({ "sunLightId", "sunLight", "sunId", "sunNode" }) do
            local v = field(t, k)
            if type(v) == "number" and v ~= 0 then table.insert(ids, { v, k }) end
        end
    end
    for _, c in ipairs(ids) do
        local ok, dx, dy, dz = pcall(localDirectionToWorld, c[1], 0, 0, 1)
        if ok and dx ~= nil and dx * dx + dz * dz > 1e-6 then
            if dy < 0 then dx, dy, dz = -dx, -dy, -dz end      -- the sun is above the horizon
            return math.atan2(dx, dz), math.deg(math.asin(math.max(-1, math.min(1, dy)))), c[2]
        end
    end
    if not self.sunLogged then
        self.sunLogged = true
        local names = {}
        for k, v in pairs(lighting or {}) do
            if type(k) == "string" and (k:lower():find("sun") or k:lower():find("light")) then
                table.insert(names, k .. "=" .. type(v))
            end
        end
        log("Sun: no sun light found (lighting has: %s)", table.concat(names, ", "))
    end
    return nil
end

-- vsSun on: camera moves around a building start on the sun side (a building can't be turned)
function VS:consoleSun(state)
    if state == "off" then self.sunSide = false
    elseif state == "on" then self.sunSide = true
    else self.sunSide = not self.sunSide end
    local yaw, up = self:sunYaw()
    return string.format("Moves start on the sun side: %s%s", self.sunSide and "on" or "off",
        yaw ~= nil and string.format(" (sun %d degrees up)", math.floor(up + 0.5)) or " (no sun found)")
end


-- ------------------------------------------------------------------ moving to a better place
-- vsMove takes the machine (the target, else what you sit in) with everything hitched to it to a flat,
-- open place where the camera can go all the way round, and vsMove back returns it (as Screenshot
-- Studio's ssMove: unhitch, move every part with physics off, physics on, hitch again). vsSpot saves
-- where you stand (the way you look) as the place for this map; Screenshot Studio's saved spot works too.
VS.SPOT_RADII = { 40, 70, 100, 140, 190, 250, 320, 400 }
VS.SPOT_ANGLES = 16
VS.SPOT_FLAT = 1.0           -- metres up or down allowed over the place
VS.SPOT_CLEARANCE = 16       -- free metres around the machine: room for the camera's moves
VS.SPOT_VIEW = 3.0           -- the camera's ring: this many times the machine's radius (+4 m) away
VS.SPOT_VIEWS = 16           -- views tested round the ring, low and high: none may hit a building
VS.spots = {}
VS.moved = nil

function VS:settingsPath() return self:getBaseDir() .. "settings.xml" end

function VS:loadSettings()
    local paths = { getUserProfileAppPath() .. "modSettings/FS25_ScreenshotStudio/settings.xml", self:settingsPath() }
    for _, path in ipairs(paths) do
        if fileExists(path) then
            local root = path:find("ScreenshotStudio", 1, true) and "screenshotStudio" or "videoStudio"
            local xml = loadXMLFile("vsSettings", path)
            if xml ~= nil and xml ~= 0 then
                for i = 0, 99 do
                    local key = string.format("%s.spots.spot(%d)", root, i)
                    local map = getXMLString(xml, key .. "#map")
                    if map == nil then break end
                    local x, z = tonumber(getXMLString(xml, key .. "#x")), tonumber(getXMLString(xml, key .. "#z"))
                    if x ~= nil and z ~= nil then
                        self.spots[map] = { x = x, z = z, yaw = tonumber(getXMLString(xml, key .. "#yaw")) or 0 }
                    end
                end
                delete(xml)
            end
        end
    end
end

function VS:saveSettings()
    createFolder(getUserProfileAppPath() .. "modSettings/")
    createFolder(self:getBaseDir())
    local xml = createXMLFile("vsSettings", self:settingsPath(), "videoStudio")
    if xml == nil or xml == 0 then return end
    local i = 0
    for map, sp in pairs(self.spots) do
        local key = string.format("videoStudio.spots.spot(%d)", i)
        setXMLString(xml, key .. "#map", map)
        setXMLString(xml, key .. "#x", string.format("%.2f", sp.x))
        setXMLString(xml, key .. "#z", string.format("%.2f", sp.z))
        setXMLString(xml, key .. "#yaw", string.format("%.4f", sp.yaw))
        i = i + 1
    end
    saveXMLFile(xml)
    delete(xml)
end

function VS:mapId()
    local info = g_currentMission ~= nil and g_currentMission.missionInfo or nil
    return tostring(info ~= nil and (info.mapId or info.mapTitle) or "map")
end

function VS:comboOf(root)
    local vehicles, combos, seen = {}, {}, {}
    local function walk(v)
        if seen[v] then return end
        seen[v] = true
        table.insert(vehicles, v)
        if v.getAttachedImplements == nil then return end
        local ok, list = pcall(v.getAttachedImplements, v)
        for _, impl in pairs(ok and list or {}) do
            local obj = type(impl) == "table" and impl.object or nil
            if type(obj) == "table" then
                local input
                if obj.getActiveInputAttacherJointDescIndex ~= nil then
                    local iok, i = pcall(obj.getActiveInputAttacherJointDescIndex, obj)
                    input = iok and i or nil
                end
                local spec = v.spec_attacherJoints
                local joint = spec ~= nil and spec.attacherJoints ~= nil and spec.attacherJoints[impl.jointDescIndex] or nil
                table.insert(combos, { vehicle = v, object = obj, joint = impl.jointDescIndex, input = input,
                    lowered = joint ~= nil and joint.moveDown or false })
                walk(obj)
            end
        end
    end
    walk(root)
    return vehicles, combos
end

function VS:posesOf(vehicles)
    local poses = {}
    for _, v in ipairs(vehicles) do
        local list, nodes = {}, {}
        for _, c in ipairs(v.components or {}) do table.insert(nodes, c.node) end
        if #nodes == 0 then nodes = { v.rootNode } end
        for _, n in ipairs(nodes) do
            local x, y, z = getWorldTranslation(n)
            local rx, ry, rz = getWorldRotation(n)
            table.insert(list, { x, y, z, rx, ry, rz })
        end
        poses[v] = list
    end
    return poses
end

-- a world rotation (Euler angles) turned by dYaw about the world's up axis. Adding dYaw to ry alone is
-- wrong whenever the engine gives the angles with rx and rz near 180 degrees (a machine facing about
-- south): so the turn is done on a helper node and read back.
local function turnedRotation(rx, ry, rz, dYaw)
    if createTransformGroup == nil or link == nil or setWorldRotation == nil or setRotation == nil
        or getRootNode == nil or delete == nil then
        return rx, ry + dYaw, rz
    end
    local ok, a, b, c = pcall(function()
        local pivot = createTransformGroup("vsTurnPivot")
        link(getRootNode(), pivot)
        local n = createTransformGroup("vsTurn")
        link(pivot, n)
        setRotation(pivot, 0, 0, 0)
        setWorldRotation(n, rx, ry, rz)
        setRotation(pivot, 0, dYaw, 0)
        local x, y, z = getWorldRotation(n)
        delete(pivot)
        return x, y, z
    end)
    if ok and a ~= nil then return a, b, c end
    return rx, ry + dYaw, rz
end

function VS:movedPoses(poses, cx, cz, x, z, dYaw)
    local c, sn = math.cos(dYaw), math.sin(dYaw)
    local out = {}
    for v, list in pairs(poses) do
        local moved = {}
        for i, q in ipairs(list) do
            local dx, dz = q[1] - cx, q[3] - cz
            local nx, nz = x + dx * c + dz * sn, z - dx * sn + dz * c
            local ny = q[2] - ground(q[1], q[3]) + ground(nx, nz) + 0.05
            local rx, ry, rz = turnedRotation(q[4], q[5], q[6], dYaw)
            moved[i] = { nx, ny, nz, rx, ry, rz }
        end
        out[v] = moved
    end
    return out
end

function VS:placeVehicles(vehicles, combos, poses)
    for i = #combos, 1, -1 do
        local cmb = combos[i]
        if cmb.vehicle.detachImplementByObject ~= nil then pcall(cmb.vehicle.detachImplementByObject, cmb.vehicle, cmb.object, true) end
    end
    for _, v in ipairs(vehicles) do
        if v.removeFromPhysics ~= nil then pcall(v.removeFromPhysics, v) end
    end
    for _, v in ipairs(vehicles) do
        local q = poses[v]
        if q ~= nil and q[1] ~= nil and v.setAbsolutePosition ~= nil then
            local parts = {}
            for i, r in ipairs(q) do parts[i] = { { r[1], r[2], r[3] }, { r[4], r[5], r[6] } } end
            local ok, err = pcall(v.setAbsolutePosition, v, q[1][1], q[1][2], q[1][3], q[1][4], q[1][5], q[1][6], parts)
            if not ok then log("Moving %s: %s", vehicleName(v), tostring(err)) end
        end
    end
    for _, v in ipairs(vehicles) do
        if v.addToPhysics ~= nil then pcall(v.addToPhysics, v) end
    end
    local lost = {}
    for _, cmb in ipairs(combos) do
        if cmb.vehicle.attachImplement ~= nil then
            pcall(cmb.vehicle.attachImplement, cmb.vehicle, cmb.object, cmb.input, cmb.joint, true, nil, cmb.lowered, false)
        end
        if cmb.object.getAttacherVehicle ~= nil then
            local ok, on = pcall(cmb.object.getAttacherVehicle, cmb.object)
            if not ok or on ~= cmb.vehicle then table.insert(lost, vehicleName(cmb.object)) end
        end
    end
    return lost
end

-- true when the camera's ring round (x, z) sees the place: rays from where the camera stands (low and
-- high) to the machine hit nothing but the ground (a shed just outside the cleared box hid the
-- Brandt roller in half its shots)
function VS:spotViewsClear(x, h0, z, radius, need)
    if raycastClosest == nil then return true end
    local ring = math.max(need, radius * self.SPOT_VIEW + 4)
    local terrain = g_currentMission ~= nil and g_currentMission.terrainRootNode or nil
    local mask = self:rayMask()
    for k = 0, self.SPOT_VIEWS - 1 do
        local b = k * 2 * math.pi / self.SPOT_VIEWS
        for _, up in ipairs({ 2.5, 9 }) do
            local px, pz = x + math.sin(b) * ring, z + math.cos(b) * ring
            local py = math.max(ground(px, pz), h0) + up
            local dx, dy, dz = x - px, h0 + 1.5 - py, z - pz
            local len = math.sqrt(dx * dx + dy * dy + dz * dz)
            local reach = len - radius * 0.5
            if reach > 1 then
                self.rayHit = nil
                pcall(raycastClosest, px, py, pz, dx / len, dy / len, dz / len, reach, "onViewRay", self, mask)
                if self.rayHit ~= nil and self.rayHit ~= terrain then
                    local obj = self:nodeObject(self.rayHit)
                    if obj == nil or not (self.spotOwn or {})[obj] then return false end
                end
            end
        end
    end
    return true
end

function VS:findSpot(vehicles, cx, cz, radius, yaw)
    local saved = self.spots[self:mapId()]
    if saved ~= nil then return { x = saved.x, z = saved.z, yaw = saved.yaw, saved = true } end
    self.spotOwn = VS.subjectSet(vehicles)
    -- first a place the camera sees from every side; else one only cleared round the machine
    return self:searchSpot(cx, cz, radius, yaw, true) or self:searchSpot(cx, cz, radius, yaw, false)
end

function VS:searchSpot(cx, cz, radius, yaw, views)
    local need = radius + self.SPOT_CLEARANCE
    local mask = self:rayMask()
    for _, r in ipairs(self.SPOT_RADII) do
        for i = 0, self.SPOT_ANGLES - 1 do
            local a = i * 2 * math.pi / self.SPOT_ANGLES
            local x, z = cx + math.sin(a) * r, cz + math.cos(a) * r
            local h0 = ground(x, z)
            local lo, hi = h0, h0
            for k = 0, 7 do
                local b = k * math.pi / 4
                for _, f in ipairs({ 0.5, 1 }) do
                    local h = ground(x + math.sin(b) * need * f, z + math.cos(b) * need * f)
                    lo, hi = math.min(lo, h), math.max(hi, h)
                end
            end
            local fits = hi - lo <= self.SPOT_FLAT + need * 0.02
            local eas = g_currentMission.environmentAreaSystem
            if fits and eas ~= nil and eas.getWaterYAtWorldPosition ~= nil then
                local ok, wy = pcall(eas.getWaterYAtWorldPosition, eas, x, h0, z)
                if ok and wy ~= nil and wy > h0 - 0.2 then fits = false end
            end
            if fits and overlapBox ~= nil then
                -- buildings, poles, cars, tree trunks, and higher up roofs and crowns over the place
                self.spotHits = 0
                pcall(overlapBox, x, h0 + 4, z, 0, 0, 0, need, 3.6, need, "onSpotHit", self, mask, true, true, true, false)
                fits = self.spotHits == 0
            end
            if fits and views then fits = self:spotViewsClear(x, h0, z, radius, need) end
            if fits then return { x = x, z = z, yaw = yaw, distance = r, views = views } end
        end
    end
    return nil
end

function VS:consoleSpot(arg)
    local map = self:mapId()
    if arg == "clear" then
        self.spots[map] = nil
        self:saveSettings()
        return "No spot on this map: vsMove finds an open, flat place by itself"
    end
    local player = g_localPlayer
    if player == nil then return "No player" end
    local x, _, z = player:getPosition()
    local yaw = 0
    local cam = g_cameraManager ~= nil and g_cameraManager:getActiveCamera() or nil
    if cam ~= nil then
        local ok, dx, _, dz = pcall(localDirectionToWorld, cam, 0, 0, -1)
        if ok and dx ~= nil then yaw = math.atan2(dx, dz) end
    end
    self.spots[map] = { x = x, z = z, yaw = yaw }
    self:saveSettings()
    return string.format("Spot for %s saved: vsMove puts machines here, facing the way you look", map)
end

-- vsMove tree: a forestry machine (the target, else what you sit in) next to a standing tree it can
-- fell, facing it with the tree in its crane's reach, on fairly flat ground with no other tree or
-- building in the way: for filming the felling. vsMove back returns it.
VS.TREE_SEARCH = { 60, 120, 200 }
VS.TREE_ANGLES = 12
VS.TREE_FLAT = 0.35          -- metres up or down under the machine: on a slope the reaching crane tips it
                             -- and Assisted Tree Felling's tilt guard stops (seen at 1.5 m: 1.5 -> 5.5 degrees)

function VS:onTreeHit(id)
    if id == nil or id == 0 or self.treeHits == nil then return true end
    local ok, tree = pcall(function()
        -- a standing, never-cut tree: the game's own test (gsTreeCut). A stump of a felled tree is static
        -- too, and a cleared wood lot is full of them: getIsSplitShapeSplit tells them apart
        if not getHasClassId(id, ClassIds.MESH_SPLIT_SHAPE or ClassIds.SHAPE) or getSplitType(id) == 0 then return false end
        if getUserAttribute ~= nil and getUserAttribute(id, "isTreeStump") == true then return false end
        if RigidBodyType ~= nil and getRigidBodyType(id) ~= RigidBodyType.STATIC then return false end  -- a felled log
        if getIsSplitShapeSplit ~= nil and getIsSplitShapeSplit(id) then return false end               -- cut: a stump
        return true
    end)
    if ok and tree then
        local x, y, z = getWorldTranslation(id)
        table.insert(self.treeHits, { id = id, x = x, y = y, z = z })
    end
    return true
end

-- the trunk's width at 0.5 m (the game's own cut test), or nil
local function trunkWidth(tree)
    if testSplitShape == nil then return nil end
    local ok, minY, maxY, minZ, maxZ = pcall(testSplitShape, tree.id, tree.x, tree.y + 0.5, tree.z, 0, 1, 0, 1, 0, 0, 3, 3)
    if not ok or minY == nil or maxY == nil then return nil end
    return math.max(maxY - minY, (maxZ or 0) - (minZ or 0))
end

function VS:moveToTree(v)
    local root = v.getRootVehicle ~= nil and v:getRootVehicle() or v
    local vehicles, combos = self:comboOf(root)
    local corners = self:cornersOf(vehicles)
    local rx, _, rz = getWorldTranslation(root.rootNode)
    local radius = 0
    for _, c in ipairs(corners) do radius = math.max(radius, math.sqrt((c[1] - rx) ^ 2 + (c[3] - rz) ^ 2)) end
    -- where the crane looks for trees (Assisted Tree Felling / the game's auto-aim), else 7 m ahead
    local aim = root.spec_automaticArmControlHarvester
    local dx, _, dz = localDirectionToWorld(root.rootNode, 0, 0, 1)
    local yaw0 = math.atan2(dx, dz)
    local reach, ox, oz, aimTurn = 7, 0, 0, 0
    if aim ~= nil and aim.treeDetectionNode ~= nil then
        local lo, hi = aim.treeDetectionNodeMinRadius or 3, aim.treeDetectionNodeMaxRadius or 9
        reach = lo + (hi - lo) * 0.25      -- close in: a long reach tips the machine
        local nx, ny, nz = getWorldTranslation(aim.treeDetectionNode)
        ox, _, oz = worldToLocal(root.rootNode, nx, ny, nz)
        -- the detection looks along its node's own forward (within its max angle), not the machine's
        local ndx, _, ndz = localDirectionToWorld(aim.treeDetectionNode, 0, 0, 1)
        if ndx ~= nil and ndx * ndx + ndz * ndz > 1e-6 then aimTurn = math.atan2(ndx, ndz) - yaw0 end
        log("vsMove tree: detection %.1f-%.1f m, max angle %s deg, node %.1f m right %.1f m ahead, looking %.0f deg off the machine's forward",
            lo, hi, aim.treeDetectionNodeMaxAngle ~= nil and string.format("%.0f", math.deg(aim.treeDetectionNodeMaxAngle)) or "?",
            ox, oz, math.deg(aimTurn))
    end
    local harvester = root.spec_woodHarvester
    local maxWidth = harvester ~= nil and harvester.cutMaxRadius ~= nil and harvester.cutMaxRadius * 2 or nil
    self.spotOwn = VS.subjectSet(vehicles)
    local mask = self:rayMask()
    if mask ~= nil and CollisionFlag ~= nil and CollisionFlag.TREE ~= nil then mask = mask - CollisionFlag.TREE end
    local function clearOfTrees(trees, target, x, z, nx, nz)
        for _, t in ipairs(trees) do
            if t ~= target then
                if (t.x - x) ^ 2 + (t.z - z) ^ 2 < (radius + 1.5) ^ 2 then return false end
                -- the head needs room: no trunk near the crane's way in, none next to the tree on this side
                -- (in a dense wood the head jams on the neighbours: "head stuck"); trees behind it don't matter
                local sx, sz = target.x - nx, target.z - nz
                local len2 = sx * sx + sz * sz
                local u = len2 > 0 and ((t.x - nx) * sx + (t.z - nz) * sz) / len2 or 0
                if u > 0 and u < 1 and (nx + sx * u - t.x) ^ 2 + (nz + sz * u - t.z) ^ 2 < 2.8 ^ 2 then return false end
                local front = (t.x - target.x) * (nx - target.x) + (t.z - target.z) * (nz - target.z) > 0
                if front and (t.x - target.x) ^ 2 + (t.z - target.z) ^ 2 < 3.0 ^ 2 then return false end
            end
        end
        return true
    end
    for _, r in ipairs(self.TREE_SEARCH) do
        self.treeHits = {}
        pcall(overlapSphere, rx, ground(rx, rz), rz, r, "onTreeHit", self, CollisionFlag.TREE, false, true, true, false)
        local trees = self.treeHits
        self.treeHits = nil
        table.sort(trees, function(a, b) return (a.x - rx) ^ 2 + (a.z - rz) ^ 2 < (b.x - rx) ^ 2 + (b.z - rz) ^ 2 end)
        for _, tree in ipairs(trees) do
            local width = trunkWidth(tree)
            if maxWidth == nil or width == nil or width <= maxWidth * 0.9 then
                for i = 0, self.TREE_ANGLES - 1 do
                    local a = i * 2 * math.pi / self.TREE_ANGLES
                    local nx, nz = tree.x + math.sin(a) * reach, tree.z + math.cos(a) * reach
                    local yaw = math.atan2(tree.x - nx, tree.z - nz) - aimTurn
                    local c, s = math.cos(yaw), math.sin(yaw)
                    local x, z = nx - (ox * c + oz * s), nz - (-ox * s + oz * c)
                    local ok = clearOfTrees(trees, tree, x, z, nx, nz)
                    if ok then
                        local h0 = ground(x, z)
                        local lo, hi = h0, h0
                        for k = 0, 7 do
                            local b = k * math.pi / 4
                            local h = ground(x + math.sin(b) * radius, z + math.cos(b) * radius)
                            lo, hi = math.min(lo, h), math.max(hi, h)
                        end
                        ok = hi - lo <= self.TREE_FLAT
                        local eas = g_currentMission.environmentAreaSystem
                        if ok and eas ~= nil and eas.getWaterYAtWorldPosition ~= nil then
                            local wok, wy = pcall(eas.getWaterYAtWorldPosition, eas, x, h0, z)
                            if wok and wy ~= nil and wy > h0 - 0.2 then ok = false end
                        end
                        if ok and overlapBox ~= nil and mask ~= nil then
                            self.spotHits = 0
                            pcall(overlapBox, x, h0 + 2.5, z, 0, yaw, 0, radius * 0.8, 2, radius * 0.8, "onSpotHit", self, mask, true, true, true, false)
                            ok = self.spotHits == 0
                        end
                    end
                    if ok then
                        local poses = self:posesOf(vehicles)
                        local lost = self:placeVehicles(vehicles, combos, self:movedPoses(poses, rx, rz, x, z, yaw - yaw0))
                        self.moved = { vehicles = vehicles, combos = combos, poses = poses, name = vehicleName(root) }
                        if aim ~= nil and aim.treeDetectionNode ~= nil then
                            local tok, tx, _, tz = pcall(worldToLocal, aim.treeDetectionNode, tree.x, tree.y, tree.z)
                            if tok and tx ~= nil then
                                log("vsMove tree: the tree is %.1f m from the detection, %.0f deg off its forward", math.sqrt(tx * tx + tz * tz), math.deg(math.atan2(tx, tz)))
                            end
                        end
                        local msg = string.format("Moved %s %.0f m, next to a tree %.1f m ahead of its crane%s",
                            vehicleName(root), math.sqrt((x - rx) ^ 2 + (z - rz) ^ 2), reach,
                            width ~= nil and string.format(" (trunk %.2f m)", width) or "")
                        if #lost > 0 then msg = msg .. "; NOT hitched again: " .. table.concat(lost, ", ") end
                        log("%s. vsMove back returns it", msg)
                        return msg
                    end
                end
            end
        end
    end
    return string.format("No tree with open ground next to it within %d m", self.TREE_SEARCH[#self.TREE_SEARCH])
end

function VS:consoleMove(arg)
    if arg == "back" then return self:moveBack() end
    if self.moved ~= nil then return "Already moved: vsMove back first" end
    if arg == "tree" then
        local t = self:getTarget()
        local tv = t ~= nil and t.vehicle or self:getSeatVehicle()
        if tv == nil then return "Nothing to move: sit in it or vsTarget it" end
        return self:moveToTree(tv)
    end
    local target = self:getTarget()
    if target ~= nil and target.placeable ~= nil then return "Buildings stay where they are" end
    local v = target ~= nil and target.vehicle or self:getSeatVehicle()
    if v == nil then return "Nothing to move: sit in it or vsTarget it" end
    local root = v.getRootVehicle ~= nil and v:getRootVehicle() or v
    local vehicles, combos = self:comboOf(root)
    local corners = self:cornersOf(vehicles)
    local lo, hi = { math.huge, math.huge }, { -math.huge, -math.huge }
    for _, c in ipairs(corners) do
        lo[1], hi[1] = math.min(lo[1], c[1]), math.max(hi[1], c[1])
        lo[2], hi[2] = math.min(lo[2], c[3]), math.max(hi[2], c[3])
    end
    local cx, cz = (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2
    local radius = math.sqrt((hi[1] - lo[1]) ^ 2 + (hi[2] - lo[2]) ^ 2) / 2
    local dx, _, dz = localDirectionToWorld(root.rootNode, 0, 0, 1)
    local yaw = math.atan2(dx, dz)
    local spot = self:findSpot(vehicles, cx, cz, radius, yaw)
    local sunYaw, sunUp, how = self:sunYaw()
    if spot ~= nil and sunYaw ~= nil and arg ~= "keep" then
        spot.yaw = sunYaw - math.rad(35)
        spot.sun = true
        log("Sun %d degrees up (%s): turned so the front three-quarter view has the sun behind the camera",
            math.floor(sunUp + 0.5), tostring(how))
    end
    if spot == nil then
        return string.format("No open, flat place within %d m: stand somewhere nice and vsSpot", self.SPOT_RADII[#self.SPOT_RADII])
    end
    local poses = self:posesOf(vehicles)
    local lost = self:placeVehicles(vehicles, combos, self:movedPoses(poses, cx, cz, spot.x, spot.z, spot.yaw - yaw))
    self.moved = { vehicles = vehicles, combos = combos, poses = poses, name = vehicleName(root) }
    local msg = string.format("Moved %s%s %s", vehicleName(root),
        #vehicles > 1 and string.format(" with %d hitched", #vehicles - 1) or "",
        spot.saved and "to your spot" or string.format("%.0f m to an open, flat place", spot.distance or 0))
        .. (spot.views == false and " (no place seen clear from every side: something may be in some views)" or "")
        .. (spot.sun and ", facing the light" or "")
    if #lost > 0 then msg = msg .. "; NOT hitched again: " .. table.concat(lost, ", ") end
    log("%s. vsMove back returns it", msg)
    return msg
end

function VS:moveBack()
    local m = self.moved
    if m == nil then return "Nothing moved" end
    local lost = self:placeVehicles(m.vehicles, m.combos, m.poses)
    self.moved = nil
    local msg = "Back where it was: " .. m.name
    if #lost > 0 then msg = msg .. "; NOT hitched again: " .. table.concat(lost, ", ") end
    log("%s", msg)
    return msg
end


-- ------------------------------------------------------------------ driving and working
-- vsDrive 8: cruise control at 8 km/h, straight on (nobody steers); vsDrive stop
function VS:drive(arg)
    local v = self:getSeatVehicle()
    if v == nil then return "Sit in the vehicle first (vsEnter)" end
    local root = v.getRootVehicle ~= nil and v:getRootVehicle() or v
    if arg == nil or arg == "stop" or arg == "0" then
        if root.setCruiseControlState ~= nil and Drivable ~= nil then
            pcall(root.setCruiseControlState, root, Drivable.CRUISECONTROL_STATE_OFF)
        end
        return "Cruise control off"
    end
    local kmh = tonumber(arg)
    if kmh == nil then return "vsDrive <km/h> or vsDrive stop" end
    self:startEngine(root)
    if root.setCruiseControlMaxSpeed ~= nil then pcall(root.setCruiseControlMaxSpeed, root, kmh, kmh) end
    if root.setCruiseControlState == nil or Drivable == nil or Drivable.CRUISECONTROL_STATE_ACTIVE == nil then
        return "This vehicle has no cruise control"
    end
    local ok, err = pcall(root.setCruiseControlState, root, Drivable.CRUISECONTROL_STATE_ACTIVE)
    if not ok then return "Cruise control failed: " .. tostring(err) end
    return string.format("Driving straight on at %g km/h (vsDrive stop)", kmh)
end

-- vsWork on: unfold, lower and switch on what is hitched, the way the game's helper starts work
function VS:work(arg)
    local v = self:getSeatVehicle()
    if v == nil then return "Sit in the vehicle first (vsEnter)" end
    local root = v.getRootVehicle ~= nil and v:getRootVehicle() or v
    local on = arg ~= "off"
    local n = 0
    if root.raiseAIEvent ~= nil then
        if on then
            pcall(root.raiseAIEvent, root, "onAIFieldWorkerStart", "onAIImplementStart")
        end
    end
    local list = {}
    if root.getChildVehicles ~= nil then
        for k, c in pairs(root:getChildVehicles() or {}) do
            local o = type(c) == "table" and c or (type(k) == "table" and k or nil)
            if o ~= nil then table.insert(list, o) end
        end
    end
    for _, o in ipairs(list) do
        if on then
            if o.aiImplementStartLine ~= nil and pcall(o.aiImplementStartLine, o) then n = n + 1 end
            if o.getCanBeTurnedOn ~= nil and o.setIsTurnedOn ~= nil then
                local ok, can = pcall(o.getCanBeTurnedOn, o)
                if ok and can then pcall(o.setIsTurnedOn, o, true) end
            end
        else
            if o.aiImplementEndLine ~= nil and pcall(o.aiImplementEndLine, o) then n = n + 1 end
            if o.setIsTurnedOn ~= nil then pcall(o.setIsTurnedOn, o, false) end
        end
    end
    if not on and root.raiseAIEvent ~= nil then
        pcall(root.raiseAIEvent, root, "onAIFieldWorkerEnd", "onAIImplementEnd")
    end
    return string.format("Work %s: %d implement(s)", on and "on (lowered, switched on)" or "off (raised)", n)
end

-- vsPower: the engine on and the machine (and what is hitched) switched on, nothing lowered or folded:
-- for "powered" keys that only work with the engine running (a harvester's crane, its saw)
function VS:power(arg)
    local v = self:getSeatVehicle()
    if v == nil then return "Sit in the vehicle first (vsEnter)" end
    local root = v.getRootVehicle ~= nil and v:getRootVehicle() or v
    local on = arg ~= "off"
    if on then self:startEngine(root) end
    local list, seen = { root }, { [root] = true }
    if root.getChildVehicles ~= nil then
        local ok, kids = pcall(root.getChildVehicles, root)
        for k, c in pairs(ok and kids or {}) do
            local o = type(c) == "table" and c or (type(k) == "table" and k or nil)
            if o ~= nil and not seen[o] then seen[o] = true; table.insert(list, o) end
        end
    end
    local n = 0
    for _, o in ipairs(list) do
        if o.setIsTurnedOn ~= nil then
            local can = true
            if on and o.getCanBeTurnedOn ~= nil then
                local ok, c = pcall(o.getCanBeTurnedOn, o)
                can = ok and c
            end
            if can and pcall(o.setIsTurnedOn, o, on) then n = n + 1 end
        end
    end
    if not on and root.stopMotor ~= nil then pcall(root.stopMotor, root) end
    local started = root.getIsMotorStarted ~= nil and select(2, pcall(root.getIsMotorStarted, root))
    return string.format("Engine %s, %d part(s) switched %s", started and "running" or "off", n, on and "on" or "off")
end

function VS:startEngine(v)
    if v == nil or v.startMotor == nil or v.getIsMotorStarted == nil then return false end
    local ok, started = pcall(v.getIsMotorStarted, v)
    if ok and not started then return (pcall(v.startMotor, v)) end
    return false
end


-- ------------------------------------------------------------------ getting in
function VS:getEnterableVehicles()
    local list = {}
    local system = g_currentMission ~= nil and g_currentMission.vehicleSystem or nil
    for _, v in ipairs(system ~= nil and system.vehicles or {}) do
        local ok, enterable = false, false
        if v.getIsEnterable ~= nil then ok, enterable = pcall(v.getIsEnterable, v) end
        if ok and enterable and v.rootNode ~= nil then table.insert(list, v) end
    end
    return list
end

function VS:enter(name)
    local player = g_localPlayer
    if player == nil or player.requestToEnterVehicle == nil then return false, "No player" end
    local current = player.getCurrentVehicle ~= nil and player:getCurrentVehicle() or nil
    local px, _, pz = player:getPosition()
    local best, bestDist
    local target = self:getTarget()
    if current ~= nil and (name == nil or name == "") and target ~= nil and target.vehicle ~= nil then
        -- already sitting in it (the list of vehicles to get into leaves out the one you are in)
        local cr = current.getRootVehicle ~= nil and current:getRootVehicle() or current
        local tr = target.vehicle.getRootVehicle ~= nil and target.vehicle:getRootVehicle() or target.vehicle
        if cr == tr then return true, "Already in " .. vehicleName(current) end
    end
    if (name == nil or name == "") and target ~= nil and target.vehicle ~= nil then
        local root = target.vehicle.getRootVehicle ~= nil and target.vehicle:getRootVehicle() or target.vehicle
        for _, v in ipairs(self:getEnterableVehicles()) do
            if v == root then
                local x, _, z = getWorldTranslation(v.rootNode)
                best, bestDist = v, MathUtil.vector2Length(x - px, z - pz)
            end
        end
    end
    if best == nil and (name == nil or name == "") and target ~= nil then
        return self:walkToTarget(target)
    end
    for _, v in ipairs(best == nil and self:getEnterableVehicles() or {}) do
        local x, _, z = getWorldTranslation(v.rootNode)
        local d = MathUtil.vector2Length(x - px, z - pz)
        local fits = name == nil or name == "" or vehicleName(v):lower():find(name:lower(), 1, true) ~= nil
        if fits and (bestDist == nil or d < bestDist) then best, bestDist = v, d end
    end
    if best == nil then return false, "No vehicle" .. (name ~= nil and name ~= "" and (" called " .. name) or "") end
    if best ~= current then
        local ok, err = pcall(player.requestToEnterVehicle, player, best)
        if not ok then return false, "Getting in failed: " .. tostring(err) end
    end
    self.pendingCamera = { vehicle = best, at = now() + 2000 }
    return true, string.format("Getting into %s (%.0f m)", vehicleName(best), bestDist)
end

function VS:checkPendingCamera()
    local p = self.pendingCamera
    if p == nil or now() < p.at then return end
    self.pendingCamera = nil
    self:startEngine(p.vehicle)
    local spec = p.vehicle.spec_enterable
    if spec == nil or p.vehicle.setActiveCameraIndex == nil then return end
    for i, cam in ipairs(spec.cameras or {}) do
        if not cam.isInside then
            pcall(p.vehicle.setActiveCameraIndex, p.vehicle, i)
            return
        end
    end
end

-- On foot, 60 m out on the side of the main view: the game loads full detail around the player
VS.WALK_DISTANCE = 60
function VS:walkToTarget(target)
    local player = g_localPlayer
    local s = self:getSubject()
    if player == nil or s == nil then return false, "Can't get to the target" end
    local f = self:frameOf(s)
    local x, _, z = self:toWorld(f, math.sin(math.rad(35)) * self.WALK_DISTANCE, 0, math.cos(math.rad(35)) * self.WALK_DISTANCE)
    local y = ground(x, z) + 0.2
    local inVehicle = player.getCurrentVehicle ~= nil and player:getCurrentVehicle() ~= nil
    local ok, err
    if inVehicle and player.leaveVehicle ~= nil then pcall(player.leaveVehicle, player) end
    if inVehicle and g_currentMission.controlledVehicle ~= nil and g_currentMission.onLeaveVehicle ~= nil then
        ok, err = pcall(g_currentMission.onLeaveVehicle, g_currentMission, x, y, z, false, false)
    elseif player.teleportTo ~= nil then
        ok, err = pcall(player.teleportTo, player, x, y, z, false, false)
    else
        ok, err = false, "no teleportTo"
    end
    if not ok then return false, "Getting to the target failed: " .. tostring(err) end
    return true, string.format("On foot %d m from %s (it has no seat), so its detail loads", self.WALK_DISTANCE, tostring(target.name))
end


-- ------------------------------------------------------------------ menus (for ui clips)
function VS:inGameMenu()
    if g_gui == nil or g_gui.screenControllers == nil or InGameMenu == nil then return nil end
    return g_gui.screenControllers[InGameMenu]
end

function VS:menuPages()
    local menu = self:inGameMenu()
    local list = {}
    if menu == nil then return list, nil end
    local known = {}
    for _, t in ipairs({ g_gui.frames or {}, g_gui.guis or {} }) do
        for n, gui in pairs(t) do
            if type(gui) == "table" then
                known[gui] = known[gui] or n
                if type(gui.target) == "table" then known[gui.target] = known[gui.target] or n end
            end
        end
    end
    local frames = menu.pageFrames
    if frames == nil and menu.pagingElement ~= nil then frames = menu.pagingElement.pages end
    for i, f in ipairs(frames or {}) do
        local frame = type(f) == "table" and f.element ~= nil and f.element or f
        local name = known[frame] or (type(frame) == "table" and (frame.name or frame.pageName)) or nil
        table.insert(list, { index = i, frame = frame, name = tostring(name or ("page " .. i)) })
    end
    return list, menu
end

-- what the in-game menu's sidebar is made of (to reach a page goToPage can't): its list/tab fields, the
-- page's button, where that button is on screen (0..1, from the bottom left) and whether it is visible
function VS:menuDiagnose(menu, frame, btn)
    local fields = {}
    for k, v in pairs(menu) do
        if type(k) == "string" and type(v) == "table" and (k:lower():find("tab") or k:lower():find("list") or k:lower():find("paging")) then
            local kind = v.setSelectedIndex ~= nil and "list" or (v.setPage ~= nil and "paging" or "table")
            table.insert(fields, k .. ":" .. kind)
        end
    end
    table.sort(fields)
    log("In-game menu fields: %s", table.concat(fields, ", "))
    if type(btn) == "table" then
        local pos, size = btn.absPosition or {}, btn.absSize or {}
        local vis = btn.getIsVisible ~= nil and select(2, pcall(btn.getIsVisible, btn))
        log("In-game menu: button of the page at %.3f, %.3f size %.3f x %.3f, visible %s, parent %s",
            tonumber(pos[1]) or -1, tonumber(pos[2]) or -1, tonumber(size[1]) or -1, tonumber(size[2]) or -1,
            tostring(vis), tostring(btn.parent ~= nil and (btn.parent.name or btn.parent.profile) or "?"))
    end
    local paging = menu.pagingElement
    if type(paging) == "table" and paging.getPageIndexByElement ~= nil then
        local ok, i = pcall(paging.getPageIndexByElement, paging, frame)
        log("In-game menu: paging index of the page %s", tostring(ok and i or "?"))
    end
end

function VS:checkPendingPage()
    local pp = self.pendingPage
    if pp == nil then return end
    pp.tries = pp.tries + 1
    if pp.menu.currentPage == pp.frame then
        self.pendingPage = nil
        log("In-game menu on page %s", pp.name)
        return
    end
    if pp.tries <= 8 then
        if pp.menu.goToPage ~= nil then pcall(pp.menu.goToPage, pp.menu, pp.frame) end
    elseif pp.tries == 9 then
        -- the page's own button in the sidebar (Settings: the gear), clicked the way the mouse does
        local tabs = pp.menu.pageTabs
        local btn = type(tabs) == "table" and (tabs[pp.frame] or tabs[pp.frame.parent]) or nil
        if type(btn) == "table" and btn.onClickCallback ~= nil then
            local ok, err = pcall(btn.onClickCallback, btn.target, btn)
            log("In-game menu: clicked the sidebar button of %s (%s)", pp.name, ok and "ok" or tostring(err))
        else
            local n = 0
            for _ in pairs(type(tabs) == "table" and tabs or {}) do n = n + 1 end
            log("In-game menu: no sidebar button for %s (%d page buttons)", pp.name, n)
        end
        self:menuDiagnose(pp.menu, pp.frame, btn)
    elseif pp.tries == 40 then
        -- the sidebar as a list: select the page's row (the way a click on its icon does)
        for k, v in pairs(pp.menu) do
            if type(k) == "string" and type(v) == "table" and v.setSelectedIndex ~= nil and k:lower():find("tab") then
                local index
                for i, p in ipairs(self:menuPages()) do if p.frame == pp.frame then index = i end end
                local ok, err = pcall(v.setSelectedIndex, v, index or 1, true)
                log("In-game menu: %s:setSelectedIndex(%s) -> %s", k, tostring(index), ok and "ok" or tostring(err))
            end
        end
    elseif pp.tries > 70 and pp.menu.onPageNext ~= nil and pp.tries % 15 == 0 then     -- after the click: a second to open
        -- goToPage didn't take: step through the pages as E does (every 15 frames: a page change takes a moment)
        pcall(pp.menu.onPageNext, pp.menu)
        local names = {}
        for _, p in ipairs(self:menuPages()) do if p.frame == pp.menu.currentPage then names[1] = p.name end end
        log("In-game menu: next page -> %s", tostring(names[1] or "?"))
    end
    if pp.tries >= 70 + 15 * 30 then
        self.pendingPage = nil
        log("In-game menu: page %s didn't open", pp.name)
    end
end

function VS:consoleMenu(...)
    local name = table.concat({ ... }, " ")
    if g_gui == nil then return "No GUI" end
    if name == "" then
        local pages = {}
        for _, p in ipairs(self:menuPages()) do table.insert(pages, p.index .. " " .. p.name) end
        local screens = {}
        for n in pairs(g_gui.guis or {}) do if type(n) == "string" then table.insert(screens, n) end end
        table.sort(screens)
        log("In-game menu pages: %s", #pages > 0 and table.concat(pages, ", ") or "none")
        log("Screens and dialogs: %s", table.concat(screens, ", "))
        return string.format("%d menu pages, %d screens/dialogs: listed in the log", #pages, #screens)
    end
    if name == "close" then
        self.pendingPage = nil
        self:closeDialogs()
        pcall(g_gui.showGui, g_gui, "")
        return "Menus closed"
    end
    local want, num = name:lower(), tonumber(name)
    local pages, menu = self:menuPages()
    for _, p in ipairs(pages) do
        if (num ~= nil and p.index == num) or (num == nil and p.name:lower():find(want, 1, true)) then
            local ok, err = pcall(g_gui.showGui, g_gui, "InGameMenu")
            if not ok then return "Opening the menu failed: " .. tostring(err) end
            self.pendingPage = { menu = menu, frame = p.frame, name = p.name, tries = 0 }
            return "In-game menu, going to page " .. p.name
        end
    end
    local hit
    for n in pairs(g_gui.guis or {}) do
        if type(n) == "string" and (hit == nil or n:lower() == want) and n:lower():find(want, 1, true) then hit = n end
    end
    if hit == nil then return "No screen, dialog or menu page called " .. name .. ": vsMenu lists them" end
    local ok, err = pcall(hit:find("Dialog") and g_gui.showDialog or g_gui.showGui, g_gui, hit)
    return ok and ("Opened " .. hit) or ("Opening " .. hit .. " failed: " .. tostring(err))
end


-- ------------------------------------------------------------------ keys
function VS.onKeyShowcase() VS:consoleShowcase() end
function VS.onKeyOrbit() VS:queueClips({ "orbit" }) end
function VS.onKeyFollow()
    if VS.clip ~= nil and VS.clip.shot == "follow" then VS:stop() else VS:queueClips({ "follow dur=0" }) end
end
function VS.onKeyLight() VS:nextLight() end
function VS.onKeyStop() VS:stop() end

if PlayerInputComponent ~= nil and PlayerInputComponent.registerGlobalPlayerActionEvents ~= nil then
    PlayerInputComponent.registerGlobalPlayerActionEvents = Utils.appendedFunction(
        PlayerInputComponent.registerGlobalPlayerActionEvents, function(self)
            for _, a in ipairs({
                { InputAction.VS_SHOWCASE, VS.onKeyShowcase },
                { InputAction.VS_ORBIT, VS.onKeyOrbit },
                { InputAction.VS_FOLLOW, VS.onKeyFollow },
                { InputAction.VS_LIGHT, VS.onKeyLight },
                { InputAction.VS_STOP, VS.onKeyStop },
            }) do
                if a[1] ~= nil then
                    local _, id = g_inputBinding:registerActionEvent(a[1], VS, a[2], false, true, false, true)
                    if id ~= nil then g_inputBinding:setActionEventTextVisibility(id, false) end
                end
            end
        end)
end


-- ------------------------------------------------------------------ console
local function joined(...) return table.concat({ ... }, " ") end

-- vsShot orbit dur=20 deg=180    one clip
function VS:consoleShot(...)
    local text = joined(...)
    if text == "" then return "vsShot <shot> [options]: vsShots lists the shots" end
    local ok, msg = self:queueClips({ text })
    return msg
end

-- vsShots: the list
function VS:consoleShots()
    for _, id in ipairs(self.SHOT_ORDER) do
        local s = self.SHOTS[id]
        log("%-9s %4.0f s  %s", id, s.dur, s.text)
    end
    log("Options: dur= ease=(linear sine inout out in smooth) fov= angle= deg= dir=-1 elev= dist= height= side=left|right " ..
        "a0= a1= e0= e1= d0= d1= lz0= ... | colors: max= config= | timelapse: from= to= (hours) | flypast: ahead= sidem= | dur=0: until vsStop")
    return string.format("%d shots listed in the log", #self.SHOT_ORDER)
end

-- vsShowcase [vehicle|quick|building|work]: a set of shots (a building gets its own set)
function VS:consoleShowcase(kind)
    if kind == nil or kind == "" then
        local s = self:getSubject()
        kind = (s ~= nil and s.kind == "building") and "building" or "vehicle"
    end
    local list = self.SHOWCASES[kind]
    if list == nil then
        local names = {}
        for k in pairs(self.SHOWCASES) do table.insert(names, k) end
        table.sort(names)
        return "Showcases: " .. table.concat(names, ", ")
    end
    local ok, msg = self:queueClips(list)
    return ok and string.format("Showcase %s: %d clips", kind, #list) or msg
end

function VS:consoleStop() return self:stop() end

function VS:consoleLight(name, hour)
    if name == nil or name == "" then return self:nextLight() end
    if name == "off" then return self:restoreLight() end
    local i = self:getLightIndex(name)
    if i == nil then
        local ids = {}
        for _, p in ipairs(self.LIGHTS) do table.insert(ids, p.id) end
        return "Unknown light. Use one of: " .. table.concat(ids, ", ") .. ", off"
    end
    return self:setLight(i, hour)
end

function VS:consoleWeather(name)
    local env = self:getEnv()
    if env == nil or name == nil then return "vsWeather sun|cloudy|rain|snow" end
    return self:setWeather(env, name:upper()) and ("Weather: " .. name) or "Weather not changed (see log)"
end

function VS:consoleVehicleLights(mode)
    mode = mode or "on"
    if mode ~= "on" and mode ~= "off" and mode ~= "beacon" and mode ~= "all" then return "vsVehicleLights on|off|beacon|all" end
    return self:setVehicleLights(mode)
end

function VS:consoleDrive(arg) return self:drive(arg) end
function VS:consoleWork(arg) return self:work(arg) end
function VS:consolePower(arg) return self:power(arg) end

-- vsUnfold: the machine being filmed (the target, else what you sit in) and everything hitched to it
-- unfolded the way it works (Foldable's turnOnFoldDirection, as Courseplay does it); vsUnfold fold folds
-- it again. A big implement filmed folded shows nothing of what it does.
function VS:consoleUnfold(arg)
    local target = self:getTarget()
    local v = target ~= nil and target.vehicle or self:getSeatVehicle()
    if v == nil then return "Nothing to unfold: sit in it or vsTarget it" end
    local root = v.getRootVehicle ~= nil and v:getRootVehicle() or v
    local vehicles = self:comboOf(root)
    local fold = arg == "fold"
    local n = 0
    for _, o in ipairs(vehicles) do
        local spec = o.spec_foldable
        if spec ~= nil and o.setFoldDirection ~= nil and (spec.foldingParts == nil or #spec.foldingParts > 0) then
            local dir = spec.turnOnFoldDirection or -1
            if dir == 0 then dir = -1 end
            if pcall(o.setFoldDirection, o, fold and -dir or dir, true) then n = n + 1 end
        end
    end
    if n == 0 then return "Nothing foldable on " .. vehicleName(root) end
    return string.format("%s %d part(s) of %s", fold and "Folding" or "Unfolding", n, vehicleName(root))
end

-- vsSave: the game saves now, while you play (a save from the pause menu happens under the menu, so what
-- a mod shows during a save, like Server Lag Watch's SERVER SAVE, can't be filmed that way). The runner
-- puts the savegame back afterwards.
function VS:consoleSave()
    local m = g_currentMission
    if m == nil or m.saveSavegame == nil then return "Can't save here" end
    local ok, err = pcall(m.saveSavegame, m)
    return ok and "Saving the game" or ("Save failed: " .. tostring(err))
end
function VS:consoleTarget(...) return self:setTarget(joined(...)) end
function VS:consoleList(...) return self:listObjects(joined(...)) end

function VS:consoleEnter(...)
    local _, msg = self:enter(joined(...))
    return msg
end

function VS:consoleFolder(name)
    self.forcedFolder = (name ~= nil and name ~= "") and safeName(name) or nil
    return "Folder: " .. (self.forcedFolder or "the subject's mod")
end

function VS:consoleFov(deg)
    self.fov = tonumber(deg)
    return string.format("Field of view: %g degrees", self.fov or self.FOV)
end

function VS:consoleQuiet(state)
    if state == "off" then self.quietEnabled = false
    elseif state == "on" then self.quietEnabled = true
    else self.quietEnabled = not self.quietEnabled end
    return "Other mods' drawing during clips: " .. (self.quietEnabled and "hidden" or "shown")
end

function VS:consoleClear(state)
    if state == "off" then self.avoidObstacles = false
    elseif state == "on" then self.avoidObstacles = true
    else self.avoidObstacles = not self.avoidObstacles end
    return "Camera moves avoid things in the way: " .. (self.avoidObstacles and "on" or "off")
end

function VS:consoleRadius(radius)
    self.placeableRadius = tonumber(radius)
    return string.format("Building size: %s", self.placeableRadius and (self.placeableRadius .. " m") or "from its placement area")
end


-- vsTab prices / vsTab 3: a tab of the open in-game menu page (Production Chains, Prices, Settings ...)
-- through the page's tab row; a page of the menu by name otherwise; nothing matching lists them (log)
function VS:consoleTab(...)
    local want = joined(...)
    local screen = g_gui ~= nil and g_gui.currentGui ~= nil and g_gui.currentGui.target or nil
    local menu = (type(screen) == "table" and screen.pageFrames ~= nil) and screen or self:inGameMenu()
    local page = menu ~= nil and menu.currentPage or nil
    if page == nil then return "No menu page open" end
    local paging = page.subCategoryPaging
    local texts = {}
    if type(paging) == "table" and paging.setState ~= nil then
        for i, text in ipairs(paging.texts or {}) do texts[i] = tostring(text) end
        local index = tonumber(want)
        if index == nil and want ~= "" then
            for i, text in ipairs(texts) do
                if index == nil and text:lower():find(want:lower(), 1, true) then index = i end
            end
        end
        if index ~= nil then
            local ok, err = pcall(paging.setState, paging, index, true)
            return ok and ("Tab " .. tostring(texts[index] or index)) or ("Switching the tab failed: " .. tostring(err))
        end
    end
    -- a tab button a mod added (Farm Inventory's INVENTORY): no paging state of its own, its click does it
    if want ~= "" and tonumber(want) == nil then
        local box = page.subCategoryBox or (page.subCategoryTabs ~= nil and page.subCategoryTabs[1] ~= nil and page.subCategoryTabs[1].parent) or nil
        local labels = {}
        for _, el in ipairs(box ~= nil and box.elements or {}) do
            local ok, text = pcall(function() return el.getText ~= nil and el:getText() or el.text end)
            text = ok and tostring(text or "") or ""
            table.insert(labels, text)
            if text:lower():find(want:lower(), 1, true) and el.onClickCallback ~= nil then
                local cok, err = pcall(el.onClickCallback, el.target, el)     -- as the button calls it
                return cok and ("Tab " .. text) or ("Clicking the tab failed: " .. tostring(err))
            end
        end
        if #labels > 0 then log("Tab buttons of this page: %s", table.concat(labels, ", ")) end
    end
    local pages = {}
    for _, p in ipairs(self:menuPages()) do
        table.insert(pages, p.name)
        if want ~= "" and p.name:lower():find(want:lower(), 1, true) and menu.goToPage ~= nil then
            local ok, err = pcall(menu.goToPage, menu, p.frame)
            return ok and ("Page " .. p.name) or ("Going to the page failed: " .. tostring(err))
        end
    end
    log("Tabs of this page: %s", #texts > 0 and table.concat(texts, ", ") or "none")
    return "No tab '" .. want .. "': the tabs are in the log"
end

-- vsSpawn <part of a shop name>: the shop item (a vehicle) loaded 25 m in front of you for this session
-- (not saved: the runner puts the savegame back) and made the target. For mods with nothing in the save.
function VS:consoleSpawn(...)
    local want = joined(...):lower()
    if want == "" or g_storeManager == nil or VehicleLoadingData == nil then return "vsSpawn <part of a shop name>" end
    local best, bestScore
    for _, item in ipairs(g_storeManager:getItems() or {}) do
        local isVehicle = item.species == nil or StoreSpecies == nil or item.species == StoreSpecies.VEHICLE
        local hay = (tostring(item.name or "") .. " " .. tostring(item.xmlFilename or "") .. " " .. tostring(item.customEnvironment or "")):lower()
        if isVehicle and hay:find(want, 1, true) then
            local score = (item.customEnvironment ~= nil and 0 or 10) + #tostring(item.name or "") / 100
            if bestScore == nil or score < bestScore then best, bestScore = item, score end
        end
    end
    if best == nil then return "No shop vehicle with '" .. want .. "' in its name, file or mod" end
    local player = g_localPlayer
    if player == nil then return "No player" end
    local px, _, pz = player:getPosition()
    local yaw = 0
    local cam = g_cameraManager ~= nil and g_cameraManager:getActiveCamera() or nil
    if cam ~= nil then
        local ok, dx, _, dz = pcall(localDirectionToWorld, cam, 0, 0, -1)
        if ok and dx ~= nil and dx * dx + dz * dz > 1e-6 then yaw = math.atan2(dx, dz) end
    end
    local x, z = px + math.sin(yaw) * 25, pz + math.cos(yaw) * 25
    local data = VehicleLoadingData.new()
    data:setStoreItem(best)
    data:setPosition(x, ground(x, z) + 0.2, z)
    data:setRotation(0, yaw + math.pi / 2, 0)
    data:setIsSaved(false)
    data:setOwnerFarmId(1)
    self.spawned = nil
    local ok, err = pcall(data.load, data, function(_, vehicles, state)
        local v = vehicles ~= nil and vehicles[1] or nil
        if v == nil or (VehicleLoadingState ~= nil and state ~= VehicleLoadingState.OK) then
            log("vsSpawn %s: didn't load (%s)", tostring(best.name), tostring(state))
            return
        end
        self.spawned = vehicles
        self.target = { vehicle = v, name = vehicleName(v) }
        log("vsSpawn: %s loaded next to you (not saved) and is the target", vehicleName(v))
    end, self, {})
    if not ok then return "Loading failed: " .. tostring(err) end
    return string.format("Loading %s (%s)", tostring(best.name), tostring(best.customEnvironment or "base game"))
end

-- vsFarmName 1 Green Valley Farm: the farm's name for this session only (not saved: the runner puts the
-- savegame back), so menus and monitors in a video show no real farm or player names
function VS:consoleFarmName(id, ...)
    local name = joined(...)
    local farmId = tonumber(id)
    if farmId == nil or name == "" then return "vsFarmName <farm id> <name>" end
    local fm = g_farmManager
    local farm = fm ~= nil and fm.getFarmById ~= nil and fm:getFarmById(farmId) or nil
    if farm == nil then return "No farm " .. tostring(farmId) end
    local old = farm.name
    farm.name = name
    log("Farm %d is called '%s' for this session (not saved)", farmId, name)
    return string.format("Farm %d: '%s' -> '%s' (this session only)", farmId, tostring(old), name)
end

function VS:consoleKeys(...)
    return "Keys for the runner: " .. joined(...)
end


-- ------------------------------------------------------------------ autorun
-- tools/fs25_video.py writes modSettings/FS25_VideoStudio/autorun.xml, starts the game with that
-- save, records the window and reads the log:
--   <autorun savegame="3" created="20261120_183000"><step>vsLight golden</step>...<step>quit</step></autorun>
-- Steps are console commands, "wait <seconds>" or "quit"; each starts when the one before is done
-- (clips included). Only in the save it names, only if less than 20 minutes old; deleted once read.
VS.AUTORUN_FILE = "autorun.xml"
VS.AUTORUN_MAX_AGE = 20
VS.AUTORUN_START_S = 12
VS.AUTORUN_PAUSE = { vsLight = 4, vsWeather = 6, vsEnter = 8, vsMenu = 2, vsKeys = 4, vsDrive = 3, vsWork = 4, vsPower = 4, vsUnfold = 10, vsTarget = 1, vsMove = 6, vsSpawn = 10, vsTab = 2 }

local function stampMinutes(stamp)
    local y, mo, d, h, mi = tostring(stamp or ""):match("^(%d%d%d%d)(%d%d)(%d%d)_(%d%d)(%d%d)")
    if y == nil then return nil end
    y, mo, d, h, mi = tonumber(y), tonumber(mo), tonumber(d), tonumber(h), tonumber(mi)
    if mo <= 2 then y = y - 1 end
    local era = math.floor(y / 400)
    local yoe = y - era * 400
    local doy = math.floor((153 * ((mo + 9) % 12) + 2) / 5) + d - 1
    local days = era * 146097 + yoe * 365 + math.floor(yoe / 4) - math.floor(yoe / 100) + doy
    return days * 1440 + h * 60 + mi
end
VS.stampMinutes = stampMinutes

function VS:readAutorun()
    local path = self:getBaseDir() .. self.AUTORUN_FILE
    if not fileExists(path) then return nil end
    local xml = loadXMLFile("vsAutorun", path)
    if xml == nil or xml == 0 then return nil end
    local save = getXMLString(xml, "autorun#savegame")
    local created = getXMLString(xml, "autorun#created")
    local steps, i = {}, 0
    while true do
        local step = getXMLString(xml, string.format("autorun.step(%d)", i))
        if step == nil then break end
        step = step:match("^%s*(.-)%s*$")
        if step ~= "" then table.insert(steps, step) end
        i = i + 1
    end
    delete(xml)
    local info = g_currentMission ~= nil and g_currentMission.missionInfo or nil
    local here = info ~= nil and tostring(info.savegameIndex) or "?"
    if save ~= here then
        log("autorun: %s is for savegame %s, this is %s: not run", self.AUTORUN_FILE, tostring(save), here)
        return nil
    end
    local age = (stampMinutes(getDate("%Y%m%d_%H%M%S")) or 0) - (stampMinutes(created) or -math.huge)
    if age < 0 or age > self.AUTORUN_MAX_AGE then
        log("autorun: %s is old (%s), not run", self.AUTORUN_FILE, tostring(created))
        removeFile(path)
        return nil
    end
    removeFile(path)
    return steps
end

function VS:checkAutorun()
    if self.autorunChecked then return end
    local info = g_currentMission ~= nil and g_currentMission.missionInfo or nil
    if info == nil or g_localPlayer == nil or g_currentMission.gameStarted == false then return end
    self.autorunChecked = true
    local steps = self:readAutorun()
    if steps == nil then return end
    self.autorun = { steps = steps, index = 0, nextAt = now() + self.AUTORUN_START_S * 1000, clips = 0 }
    log("autorun: started, %d steps, first in %d s", #steps, self.AUTORUN_START_S)
end

function VS:runStep(step)
    local words = {}
    for w in step:gmatch("%S+") do table.insert(words, w) end
    local name = table.remove(words, 1)
    if name == "wait" then return tonumber(words[1]) or 1, "waiting" end
    if name == "quit" then return 0, "quit" end
    for _, c in ipairs(self.COMMANDS) do
        if c[1] == name then
            local ok, result = pcall(self[c[3]], self, unpack(words))
            return self.AUTORUN_PAUSE[name] or 1, ok and tostring(result) or ("ERROR " .. tostring(result))
        end
    end
    return 0, "unknown step"
end

-- Dialogs the game opened by itself (a multiplayer save in single player: "The farm ... has been merged")
-- take every key and would sit in the menu clips: closed before the first step.
function VS:closeDialogs()
    if g_gui == nil then return 0 end
    local names = {}
    for _, d in ipairs(g_gui.dialogs or {}) do
        local n = type(d) == "table" and (d.name or (d.target ~= nil and d.target.name)) or nil
        table.insert(names, tostring(n or "dialog"))
    end
    if g_gui.closeAllDialogs ~= nil then pcall(g_gui.closeAllDialogs, g_gui) end
    if #names > 0 then log("Closed %d dialog(s) the game had open: %s", #names, table.concat(names, ", ")) end
    return #names
end

function VS:tickAutorun()
    local a = self.autorun
    if a == nil or self:isBusy() or now() < a.nextAt then return end
    if a.index == 0 then self:closeDialogs() end
    local step = a.steps[a.index + 1]
    a.index = a.index + 1
    if step == nil or step == "quit" then
        self.autorun = nil
        log("autorun: done, %d clip(s)", a.clips)
        if step == "quit" then
            log("autorun: quitting")
            if doExit ~= nil then pcall(doExit) end
        end
        return
    end
    local pause, result = self:runStep(step)
    log("autorun: step %d/%d %s -> %s", a.index, #a.steps, step, result)
    a.nextAt = now() + pause * 1000
end


-- ------------------------------------------------------------------ mod events
VS.COMMANDS = {
    { "vsShot", "One clip: vsShot <shot> [dur= deg= elev= dist= fov= side= ease= ...]; vsShots lists the shots", "consoleShot" },
    { "vsShots", "Lists the shots and their options (in the log)", "consoleShots" },
    { "vsShowcase", "A set of clips of what you sit in or the target: [vehicle|quick|building|work]", "consoleShowcase" },
    { "vsStop", "Ends the clip now and clears the queue", "consoleStop" },
    { "vsLight", "Light preset: golden, morning, midday, overcast, dawn, night, off [hour]; empty = next", "consoleLight" },
    { "vsWeather", "Weather: sun, cloudy, rain, snow", "consoleWeather" },
    { "vsVehicleLights", "The subject's lights: on, off, beacon, all", "consoleVehicleLights" },
    { "vsDrive", "Cruise control straight on: <km/h>, or stop", "consoleDrive" },
    { "vsMove", "The machine with what is hitched to it to your vsSpot or an open, flat place; [tree] = next to a tree its crane can fell; [back] = where it was", "consoleMove" },
    { "vsSun", "Camera moves around a building start on the sun side: on/off (vsMove turns vehicles to the light)", "consoleSun" },
    { "vsSpot", "Here (where you stand, the way you look) is where vsMove puts machines on this map; [clear]", "consoleSpot" },
    { "vsWork", "Unfold, lower and switch on what is hitched: on/off", "consoleWork" },
    { "vsUnfold", "Unfold the machine being filmed and what is hitched to it, as it works: [fold] folds it again", "consoleUnfold" },
    { "vsSave", "The game saves now, while you play (filming what a mod shows during a save)", "consoleSave" },
    { "vsPower", "Engine on and the machine switched on (powered keys: a harvester's crane and saw): on/off", "consolePower" },
    { "vsTarget", "What to film: the nearest vehicle, implement or building with [name] in its name; empty = what you sit in", "consoleTarget" },
    { "vsList", "Vehicles, implements and buildings near you, or all with [name] in their name", "consoleList" },
    { "vsEnter", "Get into the target, the nearest vehicle, or the one with [name]; outside camera", "consoleEnter" },
    { "vsMenu", "Open a screen, dialog or in-game menu page (for ui clips): [name]; empty = list; close", "consoleMenu" },
    { "vsKeys", "For the runner: keys it types into the game, e.g. ctrl+f tractor enter", "consoleKeys" },
    { "vsTab", "A tab of the open menu page by name or number; nothing matching lists them (log)", "consoleTab" },
    { "vsSpawn", "A shop vehicle loaded in front of you for this session (not saved) as the target: <part of its name>", "consoleSpawn" },
    { "vsFarmName", "A farm's name for this session only (not saved): <farm id> <name>", "consoleFarmName" },
    { "vsFolder", "Folder name for the next clips, empty = the subject's mod", "consoleFolder" },
    { "vsFov", "Field of view for the shots in degrees [40]", "consoleFov" },
    { "vsQuiet", "Hide other mods' drawing (Courseplay, AutoDrive, hints) during clips: on/off", "consoleQuiet" },
    { "vsClear", "Camera moves go around walls, poles, trees and cars in the way: on/off", "consoleClear" },
    { "vsRadius", "Size of a building in metres (when its placement area is wrong)", "consoleRadius" },
}

function VS:loadMap()
    self:engineDrawing()
    self:loadSettings()
    for _, c in ipairs(self.COMMANDS) do addConsoleCommand(c[1], c[2], c[3], self) end
    local mod = g_modManager ~= nil and g_modManager.getModByName ~= nil and g_modManager:getModByName(self.MOD_NAME) or nil
    self.version = mod ~= nil and mod.version or nil
    log("Loaded %s. Right Shift + 1 showcase, 2 orbit, 3 follow, 4 light, 0 stop. vsShots lists the shots.",
        tostring(self.version or ""))
end

function VS:deleteMap()
    if self.run ~= nil then
        self.clip = nil
        self:finishRun()
    end
    self:setQuiet(false)
    self:deleteCopies()
    self:showOriginals(true)
    if self.moved ~= nil then self:moveBack() end
    for _, c in ipairs(self.COMMANDS) do removeConsoleCommand(c[1]) end
    if self.camera ~= nil then
        g_cameraManager:removeCamera(self.camera)
        delete(self.camera)
        self.camera = nil
    end
    self.light, self.lightSaved = nil, nil
    self.autorun, self.autorunChecked, self.pendingCamera = nil, nil, nil
    self.target, self.queue, self.marker = nil, {}, nil
end

function VS:update(dt)
    if self.muted ~= nil and self.run == nil then self:setQuiet(false) end   -- never left muted
    self:tick()
    self:checkPendingCamera()
    self:checkAutorun()
    self:tickAutorun()
end

function VS:draw()
    self:drawMarker("draw")
end

-- An open menu pauses the mission's update; the GUI still updates and draws every frame: ui clips
-- (and the autorun) go on from there, and the cards are drawn over the menus.
if Gui ~= nil and Gui.update ~= nil then
    Gui.update = Utils.appendedFunction(Gui.update, function()
        VS:tick()
        VS:checkPendingPage()
        VS:tickAutorun()
    end)
end
if Gui ~= nil and Gui.draw ~= nil then
    Gui.draw = Utils.appendedFunction(Gui.draw, function() VS:drawMarker("gui") end)
end

addModEventListener(VS)
