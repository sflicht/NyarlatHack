return function(c)
  local h = c.history
  local echo = h[1]
  local newest = echo
  if h[2] then newest = h[2] end
  if h[3] then newest = h[3] end
  if h[4] then newest = h[4] end
  if h[5] then newest = h[5] end
  if h[6] then newest = h[6] end
  if h[7] then newest = h[7] end
  if h[8] then newest = h[8] end
  local dx = 0
  local dy = 0
  if echo.x > c.mx then dx = 1 elseif echo.x < c.mx then dx = -1 end
  if echo.y > c.my then dy = 1 elseif echo.y < c.my then dy = -1 end
  local s = c.state
  if s < 0 or s > 1000000 then s = 0 end
  local glass = s % 3
  if glass == 1 then
    local swap = dx
    dx = dy
    dy = swap
  elseif glass == 2 then
    dx = -dx
    dy = -dy
  end
  local ax = newest.x - c.mx
  if ax < 0 then ax = -ax end
  local ay = newest.y - c.my
  if ay < 0 then ay = -ay end
  local near = ax
  if ay > near then near = ay end
  if near <= 1 then
    dx = 0
    dy = 0
    if newest.x > c.mx then dx = -1 elseif newest.x < c.mx then dx = 1 end
    if newest.y > c.my then dy = -1 elseif newest.y < c.my then dy = 1 end
  end
  if dx == 0 and dy == 0 then
    if glass == 0 then dx = 1 elseif glass == 1 then dy = 1 else dx = -1 end
  end
  s = s + 1
  if s > 1000000 then s = 0 end
  return {dx = dx, dy = dy, state = s}
end
