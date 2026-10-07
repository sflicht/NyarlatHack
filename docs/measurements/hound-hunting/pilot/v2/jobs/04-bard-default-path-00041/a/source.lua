return function(c)
  local s = c.state
  if s < 0 then s = 0 end
  if s > 1000000 then s = 0 end
  local ns = s + 1
  if ns > 1000000 then ns = 0 end
  if s % 4 == 3 then
    return {dx=0, dy=0, state=ns}
  end
  local h = c.history
  if h == nil or h[1] == nil then
    return {dx=0, dy=0, state=ns}
  end
  local n = 1
  if h[2] ~= nil then n = 2 end
  if h[3] ~= nil then n = 3 end
  if h[4] ~= nil then n = 4 end
  if h[5] ~= nil then n = 5 end
  if h[6] ~= nil then n = 6 end
  if h[7] ~= nil then n = 7 end
  if h[8] ~= nil then n = 8 end
  local back = 0
  if s % 4 == 1 then
    back = 1
    if s % 8 == 1 then back = 2 end
  end
  local i = n - back
  if i < 1 then i = 1 end
  local t = h[i]
  if t == nil or t.x == nil or t.y == nil then
    i = n
    t = h[n]
  end
  if t == nil or t.x == nil or t.y == nil then
    return {dx=0, dy=0, state=ns}
  end
  local dx = 0
  local dy = 0
  if t.x > c.mx then dx = 1 elseif t.x < c.mx then dx = -1 end
  if t.y > c.my then dy = 1 elseif t.y < c.my then dy = -1 end
  if dx == 0 and dy == 0 and i ~= n then
    t = h[n]
    if t ~= nil and t.x ~= nil and t.y ~= nil then
      if t.x > c.mx then dx = 1 elseif t.x < c.mx then dx = -1 end
      if t.y > c.my then dy = 1 elseif t.y < c.my then dy = -1 end
    end
  end
  return {dx=dx, dy=dy, state=ns}
end
