return function(c)
  local s = c.state + 1
  if s > 1000000 then s = 0 end
  local n = #c.history
  local live = c.history[n]
  local rx = live.x - c.mx
  local ry = live.y - c.my
  local ax = rx
  local ay = ry
  if ax < 0 then ax = -ax end
  if ay < 0 then ay = -ay end
  local span = ax
  if ay > span then span = ay end
  if span <= 2 then
    local dx = 0
    local dy = 0
    if rx > 0 then dx = -1 elseif rx < 0 then dx = 1 end
    if ry > 0 then dy = -1 elseif ry < 0 then dy = 1 end
    if dx == 0 and dy == 0 then dx = 1 end
    return {dx=dx, dy=dy, state=s}
  end
  if s % 4 == 0 then
    return {dx=0, dy=0, state=s}
  end
  local idx = 1
  if s % 4 == 3 and n >= 3 then idx = 2 end
  local echo = c.history[idx]
  local dx = 0
  local dy = 0
  if echo.x > c.mx then dx = 1 elseif echo.x < c.mx then dx = -1 end
  if echo.y > c.my then dy = 1 elseif echo.y < c.my then dy = -1 end
  return {dx=dx, dy=dy, state=s}
end
