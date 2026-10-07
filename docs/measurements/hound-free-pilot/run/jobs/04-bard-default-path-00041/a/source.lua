return function(c)
  local h = c.history
  local n = #h
  if n < 1 then n = 1 end
  if n > 8 then n = 8 end
  local s = c.state
  if s < 0 then s = 0 end
  if s > 1000000 then s = 0 end
  local beat = s % 4
  local pressure = s % 16
  local echo = h[1]
  local now = h[n]
  local mx = c.mx
  local my = c.my
  local ex = echo.x
  local ey = echo.y
  local px = now.x
  local py = now.y
  local dx = 0
  local dy = 0
  if beat ~= 2 and not (beat == 0 and pressure >= 12) then
    if ex ~= mx or ey ~= my then
      if ex > mx then dx = 1 elseif ex < mx then dx = -1 end
      if ey > my then dy = 1 elseif ey < my then dy = -1 end
      if beat == 1 then dy = 0 end
      if beat == 3 then dx = 0 end
    end
  end
  if beat == 3 and n >= 2 then
    local vx = h[2].x - ex
    local vy = h[2].y - ey
    if vx > 1 then vx = 1 elseif vx < -1 then vx = -1 end
    if vy > 1 then vy = 1 elseif vy < -1 then vy = -1 end
    if vx ~= 0 or vy ~= 0 then
      dx = 0
      dy = 0
      if vx ~= 0 then dx = vx else dy = vy end
    end
  end
  if beat == 0 and (ex == mx or ey == my) then
    dx = 0
    dy = 0
  end
  local cx = px - (mx + dx)
  local cy = py - (my + dy)
  if cx < 0 then cx = -cx end
  if cy < 0 then cy = -cy end
  local nd = cx
  if cy > cx then nd = cy end
  local ox = px - mx
  local oy = py - my
  if ox < 0 then ox = -ox end
  if oy < 0 then oy = -oy end
  local od = ox
  if oy > ox then od = oy end
  if od <= 1 then
    dx = 0
    dy = 0
    if px > mx then dx = -1 elseif px < mx then dx = 1 end
    if py > my then dy = -1 elseif py < my then dy = 1 end
    if dx == 0 and dy == 0 then
      if beat % 2 == 0 then dx = 1 else dy = -1 end
    end
  elseif nd <= 1 then
    dx = 0
    dy = 0
  end
  if dx == 0 and dy == 0 and beat == 1 and od >= 3 then
    if px > mx then dx = -1 elseif px < mx then dx = 1 else dy = 1 end
  end
  local ns = s + 1
  if ns > 1000000 then ns = 0 end
  return {dx = dx, dy = dy, state = ns}
end
