return function(c)
  local s0 = c.state
  if s0 == nil or s0 < 0 then
    s0 = 0
  end
  if s0 > 1000000 then
    s0 = 1000000
  end
  local s = (s0 % 1000000) + 1
  local h = c.history
  if h == nil then
    return {dx = 0, dy = 0, state = s}
  end
  local n = #h
  if n < 1 then
    return {dx = 0, dy = 0, state = s}
  end
  if n > 8 then
    n = 8
  end
  local beat = s % 5
  if beat == 0 or beat == 4 then
    return {dx = 0, dy = 0, state = s}
  end
  local lag = 0
  if beat == 2 then
    lag = 1
  elseif beat == 3 then
    lag = 2
  end
  local idx = n - lag
  if idx < 1 then
    idx = 1
  end
  local t = h[idx]
  if t == nil then
    t = h[n]
  end
  if t == nil or t.x == nil or t.y == nil then
    return {dx = 0, dy = 0, state = s}
  end
  local dx = 0
  local dy = 0
  if t.x > c.mx then
    dx = 1
  elseif t.x < c.mx then
    dx = -1
  end
  if t.y > c.my then
    dy = 1
  elseif t.y < c.my then
    dy = -1
  end
  return {dx = dx, dy = dy, state = s}
end
