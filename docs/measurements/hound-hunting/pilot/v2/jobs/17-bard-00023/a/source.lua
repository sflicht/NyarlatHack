-- The hound answers a footprint not yet left, then is silent two beats so the silence can catch up.
return function(c)
  local s = c.state
  if s == nil or s < 0 or s > 1000000 then s = 0 end
  s = s + 1
  if s > 1000000 then s = 1 end
  local beat = s % 5
  if beat == 0 or beat == 4 then
    return {dx = 0, dy = 0, state = s}
  end
  local h = c.history
  local n = 0
  if h ~= nil then n = #h end
  if n < 1 then
    return {dx = 0, dy = 0, state = s}
  end
  if n > 8 then n = 8 end
  local idx = n
  if beat == 2 then
    idx = n - 2
    if idx < 1 then idx = 1 end
  end
  local p = h[idx]
  if p == nil or p.x == nil or p.y == nil or c.mx == nil or c.my == nil then
    return {dx = 0, dy = 0, state = s}
  end
  local dx = 0
  local dy = 0
  if p.x > c.mx then dx = 1 end
  if p.x < c.mx then dx = -1 end
  if p.y > c.my then dy = 1 end
  if p.y < c.my then dy = -1 end
  return {dx = dx, dy = dy, state = s}
end
