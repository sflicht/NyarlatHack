return function(c)
  local st = c.state
  if st < 0 then st = 0 end
  if st > 1000000 then st = 0 end
  local shy = st % 5
  local rest = st // 5
  local beat = rest % 4
  local dir = (rest // 4) % 9
  local ldx = (dir % 3) - 1
  local ldy = (dir // 3) - 1
  local h = c.history
  local n = 0
  if h ~= nil then n = #h end
  local curx = c.mx
  local cury = c.my
  local near = 0
  if n >= 1 then
    curx = h[n].x
    cury = h[n].y
    local ax = curx - c.mx
    local ay = cury - c.my
    if ax < 0 then ax = -ax end
    if ay < 0 then ay = -ay end
    local d = ay
    if ax > ay then d = ax end
    if d <= 1 then near = 1 end
  end
  if near == 1 then shy = 4 end
  local dx = 0
  local dy = 0
  local nextshy = shy
  local nd = dir
  if shy > 0 then
    nextshy = shy - 1
    local sx = c.mx - curx
    local sy = c.my - cury
    if sx > 0 then dx = 1 elseif sx < 0 then dx = -1 else dx = 0 end
    if sy > 0 then dy = 1 elseif sy < 0 then dy = -1 else dy = 0 end
    if dx == 0 and dy == 0 then
      if (beat % 2) == 0 then dx = 1 else dx = -1 end
    end
    nd = (dx + 1) + (dy + 1) * 3
  elseif beat == 3 then
    dx = 0
    dy = 0
  else
    if n >= 1 then
      local idx = 1
      if beat == 1 and n >= 2 then idx = 2 end
      local p = h[idx]
      local tx = p.x - c.mx
      local ty = p.y - c.my
      if tx > 0 then dx = 1 elseif tx < 0 then dx = -1 else dx = 0 end
      if ty > 0 then dy = 1 elseif ty < 0 then dy = -1 else dy = 0 end
    end
    if dx == 0 and dy == 0 then
      dx = ldx
      dy = ldy
      if dx == 0 and dy == 0 then dx = 1 end
    end
    if n >= 1 then
      local ax2 = curx - (c.mx + dx)
      local ay2 = cury - (c.my + dy)
      if ax2 < 0 then ax2 = -ax2 end
      if ay2 < 0 then ay2 = -ay2 end
      local d2 = ay2
      if ax2 > ay2 then d2 = ax2 end
      if d2 <= 1 then
        local sx = c.mx - curx
        local sy = c.my - cury
        if sx > 0 then dx = 1 elseif sx < 0 then dx = -1 else dx = 0 end
        if sy > 0 then dy = 1 elseif sy < 0 then dy = -1 else dy = 0 end
        if dx == 0 and dy == 0 then
          if (beat % 2) == 0 then dx = 1 else dx = -1 end
        end
        nextshy = 3
      end
    end
    nd = (dx + 1) + (dy + 1) * 3
  end
  local nextbeat = beat + 1
  if nextbeat > 3 then nextbeat = 0 end
  local ns = nextshy + 5 * (nextbeat + 4 * nd)
  if ns < 0 then ns = 0 end
  if ns > 1000000 then ns = 0 end
  return {dx = dx, dy = dy, state = ns}
end
