return function(c)
  local s = c.state
  if s == nil or s < 0 then s = 0 end
  if s > 1000000 then s = 0 end
  local ns = s + 1
  if ns > 1000000 then ns = 0 end
  local h = c.history
  local n = 0
  if h ~= nil and h[1] ~= nil then n = 1 end
  if h ~= nil and h[2] ~= nil then n = 2 end
  if h ~= nil and h[3] ~= nil then n = 3 end
  if h ~= nil and h[4] ~= nil then n = 4 end
  if h ~= nil and h[5] ~= nil then n = 5 end
  if h ~= nil and h[6] ~= nil then n = 6 end
  if h ~= nil and h[7] ~= nil then n = 7 end
  if h ~= nil and h[8] ~= nil then n = 8 end
  local dx = 0
  local dy = 0
  if n == 0 then
    if s % 2 == 0 then dx = 1 else dx = -1 end
    return {dx = dx, dy = dy, state = ns}
  end
  local px = h[n].x
  local py = h[n].y
  local ax = px - c.mx
  local ay = py - c.my
  if ax < 0 then ax = -ax end
  if ay < 0 then ay = -ay end
  local dist = ax
  if ay > dist then dist = ay end
  if dist <= 1 then
    if px > c.mx then dx = -1 elseif px < c.mx then dx = 1 end
    if py > c.my then dy = -1 elseif py < c.my then dy = 1 end
    if dx == 0 and dy == 0 then
      if s % 2 == 0 then dx = 1 else dx = -1 end
    end
    return {dx = dx, dy = dy, state = ns}
  end
  local beat = s % 4
  if beat == 3 then
    return {dx = 0, dy = 0, state = ns}
  end
  local tx = h[1].x
  local ty = h[1].y
  local sx = 0
  local sy = 0
  local mis = 0
  if n >= 2 then
    local fx = h[2].x - h[1].x
    local fy = h[2].y - h[1].y
    local lx = h[n].x - h[n - 1].x
    local ly = h[n].y - h[n - 1].y
    local fsx = 0
    local fsy = 0
    local lsx = 0
    local lsy = 0
    if fx > 0 then fsx = 1 elseif fx < 0 then fsx = -1 end
    if fy > 0 then fsy = 1 elseif fy < 0 then fsy = -1 end
    if lx > 0 then lsx = 1 elseif lx < 0 then lsx = -1 end
    if ly > 0 then lsy = 1 elseif ly < 0 then lsy = -1 end
    if (fsx ~= 0 or fsy ~= 0) and fsx == -lsx and fsy == -lsy then
      mis = 1
      sx = fsx
      sy = fsy
    end
  end
  if mis == 0 then
    if tx > c.mx then sx = 1 elseif tx < c.mx then sx = -1 end
    if ty > c.my then sy = 1 elseif ty < c.my then sy = -1 end
  end
  if beat == 0 then
    dx = sx
  elseif beat == 1 then
    dy = sy
  else
    dx = sx
    dy = sy
  end
  if dx == 0 and dy == 0 then
    if tx > c.mx then
      dx = 1
    elseif tx < c.mx then
      dx = -1
    elseif ty > c.my then
      dy = 1
    elseif ty < c.my then
      dy = -1
    elseif s % 2 == 0 then
      dx = 1
    else
      dx = -1
    end
  end
  local qx = c.mx + dx
  local qy = c.my + dy
  local rx = qx - px
  local ry = qy - py
  if rx < 0 then rx = -rx end
  if ry < 0 then ry = -ry end
  if rx <= 1 and ry <= 1 then
    dx = 0
    dy = 0
    if px > c.mx then dx = -1 elseif px < c.mx then dx = 1 end
    if py > c.my then dy = -1 elseif py < c.my then dy = 1 end
  end
  return {dx = dx, dy = dy, state = ns}
end
