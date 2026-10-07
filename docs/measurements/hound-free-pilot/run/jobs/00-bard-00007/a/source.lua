return function(c)
  local phase = 0
  if c.state ~= nil and c.state >= 0 then
    phase = c.state % 3
  end
  local nxt = 0
  if phase < 2 then
    nxt = phase + 1
  end
  local h = c.history
  local n = #h
  if n < 1 then
    return {dx = 1, dy = 0, state = nxt}
  end
  local newest = h[n]
  local ax = newest.x - c.mx
  local ay = newest.y - c.my
  local absx = ax
  local absy = ay
  if absx < 0 then absx = -absx end
  if absy < 0 then absy = -absy end
  local sep = absx
  if absy > sep then sep = absy end
  if phase == 2 and sep >= 3 then
    return {dx = 0, dy = 0, state = nxt}
  end
  local echo = h[1]
  local tx = echo.x
  local ty = echo.y
  if n >= 2 then
    local ox = h[1].x - h[2].x
    local oy = h[1].y - h[2].y
    local aox = ox
    local aoy = oy
    if aox < 0 then aox = -aox end
    if aoy < 0 then aoy = -aoy end
    if aox >= aoy then
      if ox > 0 then
        tx = echo.x + 1
      elseif ox < 0 then
        tx = echo.x - 1
      end
    else
      if oy > 0 then
        ty = echo.y + 1
      elseif oy < 0 then
        ty = echo.y - 1
      end
    end
  end
  local sx = tx - c.mx
  local sy = ty - c.my
  local dx = 0
  local dy = 0
  if phase ~= 1 then
    if sx > 0 then
      dx = 1
    elseif sx < 0 then
      dx = -1
    elseif sy > 0 then
      dy = 1
    elseif sy < 0 then
      dy = -1
    end
  else
    if sy > 0 then
      dy = 1
    elseif sy < 0 then
      dy = -1
    elseif sx > 0 then
      dx = 1
    elseif sx < 0 then
      dx = -1
    end
  end
  local landx = ax - dx
  local landy = ay - dy
  if landx < 0 then landx = -landx end
  if landy < 0 then landy = -landy end
  local near = landx
  if landy > near then near = landy end
  if (dx == 0 and dy == 0) or near < 2 then
    dx = 0
    dy = 0
    if absx >= absy then
      if ax > 0 then
        dx = -1
      else
        dx = 1
      end
    else
      if ay > 0 then
        dy = -1
      else
        dy = 1
      end
    end
  end
  return {dx = dx, dy = dy, state = nxt}
end
