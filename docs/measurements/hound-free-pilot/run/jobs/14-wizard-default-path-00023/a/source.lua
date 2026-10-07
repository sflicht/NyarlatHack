return function(c)
  local h = c.history
  local n = #h
  local s = c.state
  local dx = 0
  local dy = 0
  if s % 3 == 0 then
    local p = h[n]
    local rx = c.mx - p.x
    local ry = c.my - p.y
    local ax = rx
    if ax < 0 then ax = -ax end
    local ay = ry
    if ay < 0 then ay = -ay end
    if ax <= 1 and ay <= 1 then
      if ay > ax then
        if ry > 0 then dy = 1 elseif ry < 0 then dy = -1 end
      else
        if rx > 0 then dx = 1 elseif rx < 0 then dx = -1 else dx = 1 end
      end
    else
      local i = 1
      if n > 4 then i = n - 4 end
      local t = h[i]
      local px = t.x - c.mx
      local py = t.y - c.my
      if n >= 3 then
        local b = h[n - 1]
        local d = h[n - 2]
        local ux = b.x - d.x
        local uy = b.y - d.y
        local vx = p.x - b.x
        local vy = p.y - b.y
        if ux + vx == 0 and uy + vy == 0 and (ux ~= 0 or uy ~= 0) then
          px = ux
          py = uy
        end
      end
      local ex = px
      if ex < 0 then ex = -ex end
      local ey = py
      if ey < 0 then ey = -ey end
      if ey > ex then
        if py > 0 then dy = 1 elseif py < 0 then dy = -1 end
      else
        if px > 0 then dx = 1 elseif px < 0 then dx = -1 end
      end
      if c.mx + dx == p.x and c.my + dy == p.y then
        dx = 0
        dy = 0
      end
    end
  end
  local ns = s + 1
  if ns > 1000000 then ns = 0 end
  return {dx = dx, dy = dy, state = ns}
end
