return function(c)
  local h = c.history
  local n = #h
  local s = c.state
  if s == nil then s = 0 end
  if s < 0 or s > 1000000 then s = 0 end
  local ns = s + 1
  if ns > 1000000 then ns = 0 end
  if n < 1 then return {dx = 0, dy = 0, state = ns} end
  local px = h[n].x
  local py = h[n].y
  local adx = px - c.mx
  local ady = py - c.my
  if adx < 0 then adx = -adx end
  if ady < 0 then ady = -ady end
  local near = adx
  if ady > near then near = ady end
  if near <= 1 then
    local dx = 0
    local dy = 0
    if adx >= ady then
      if c.mx >= px then dx = 1 else dx = -1 end
    else
      if c.my >= py then dy = 1 else dy = -1 end
    end
    return {dx = dx, dy = dy, state = ns}
  end
  local phase = s % 6
  if phase == 0 or phase == 3 then return {dx = 0, dy = 0, state = ns} end
  local rev = false
  local ox = 0
  local oy = 0
  if n >= 3 then
    local ux = h[n - 1].x - h[n - 2].x
    local uy = h[n - 1].y - h[n - 2].y
    local vx = h[n].x - h[n - 1].x
    local vy = h[n].y - h[n - 1].y
    ox = ux
    oy = uy
    if ux * vx + uy * vy < 0 then rev = true end
  end
  local dx = 0
  local dy = 0
  if rev then
    if phase % 2 == 1 then
      if ox > 0 then dx = 1 elseif ox < 0 then dx = -1
      elseif oy > 0 then dy = 1 elseif oy < 0 then dy = -1 end
    else
      if oy > 0 then dy = 1 elseif oy < 0 then dy = -1
      elseif ox > 0 then dx = 1 elseif ox < 0 then dx = -1 end
    end
  else
    local idx = 1
    if n >= 2 and h[1].x == c.mx and h[1].y == c.my then idx = 2 end
    local tx = h[idx].x
    local ty = h[idx].y
    local sx = 0
    local sy = 0
    if tx > c.mx then sx = 1 elseif tx < c.mx then sx = -1 end
    if ty > c.my then sy = 1 elseif ty < c.my then sy = -1 end
    if phase % 2 == 1 then
      dx = sx
      if dx == 0 then dy = sy end
    else
      dy = sy
      if dy == 0 then dx = sx end
    end
    if phase == 5 then
      dx = -dx
      dy = -dy
    end
  end
  if dx ~= 0 or dy ~= 0 then
    local nx = c.mx + dx - px
    local ny = c.my + dy - py
    if nx < 0 then nx = -nx end
    if ny < 0 then ny = -ny end
    local nd = nx
    if ny > nd then nd = ny end
    if nd <= 1 then
      dx = 0
      dy = 0
      if phase % 2 == 1 then
        if c.my >= py then dy = 1 else dy = -1 end
      else
        if c.mx >= px then dx = 1 else dx = -1 end
      end
      nx = c.mx + dx - px
      ny = c.my + dy - py
      if nx < 0 then nx = -nx end
      if ny < 0 then ny = -ny end
      nd = nx
      if ny > nd then nd = ny end
      if nd <= 1 then dx = 0 dy = 0 end
    end
  end
  return {dx = dx, dy = dy, state = ns}
end
