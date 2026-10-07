return function(c)
  -- A salt-pitted collar bell skips one tick; that thin miss is how far the echo seems.
  local s = c.state
  if s == nil then s = 0 end
  s = s + 1
  if s > 1000000 then s = 1 end
  if s % 4 == 0 then
    return {dx = 0, dy = 0, state = s}
  end
  local h = c.history
  local n = #h
  if n < 1 then
    return {dx = 0, dy = 0, state = s}
  end
  local back = s % 3
  if back > n - 1 then back = n - 1 end
  local echo = h[n - back]
  local sx = echo.x - c.mx
  local sy = echo.y - c.my
  local dx = 0
  local dy = 0
  if sx > 0 then dx = 1 elseif sx < 0 then dx = -1 end
  if sy > 0 then dy = 1 elseif sy < 0 then dy = -1 end
  return {dx = dx, dy = dy, state = s}
end
