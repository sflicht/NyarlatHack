return function(c)
  local s = c.state + 1
  if s > 1000000 then
    s = 1
  end
  local phase = s % 16
  if phase > 12 then
    return {dx = 0, dy = 0, state = s}
  end
  if c.history == nil then
    return {dx = 0, dy = 0, state = s}
  end
  local n = 0
  if c.history[1] ~= nil then
    n = 1
  end
  if c.history[2] ~= nil then
    n = 2
  end
  if c.history[3] ~= nil then
    n = 3
  end
  if c.history[4] ~= nil then
    n = 4
  end
  if c.history[5] ~= nil then
    n = 5
  end
  if c.history[6] ~= nil then
    n = 6
  end
  if c.history[7] ~= nil then
    n = 7
  end
  if c.history[8] ~= nil then
    n = 8
  end
  if n < 1 then
    return {dx = 0, dy = 0, state = s}
  end
  local idx = n
  if (phase == 2 or phase == 9) and n > 1 then
    idx = n - 1
  end
  local t = c.history[idx]
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
  if dx == 0 and dy == 0 and idx < n then
    t = c.history[n]
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
  end
  return {dx = dx, dy = dy, state = s}
end
