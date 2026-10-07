return function(c)
  local h = c.history
  local n = 0
  if h ~= nil then n = #h end
  local st = 0
  if c.state ~= nil then st = c.state end
  if st < 0 then st = 0 end
  if st > 1000000 then st = 1000000 end
  local nxt = st + 1
  if nxt > 1000000 then nxt = 0 end
  if n < 1 then
    return {dx = 0, dy = 0, state = nxt}
  end
  local px = h[n].x
  local py = h[n].y
  local mx = c.mx
  local my = c.my
  local rx = px - mx
  local ry = py - my
  local ax = rx
  if ax < 0 then ax = -ax end
  local ay = ry
  if ay < 0 then ay = -ay end
  local near = ax
  if ay > near then near = ay end
  if near <= 1 then
    local dx = 0
    local dy = 0
    if rx > 0 then dx = -1 elseif rx < 0 then dx = 1 end
    if ry > 0 then dy = -1 elseif ry < 0 then dy = 1 end
    if dx == 0 and dy == 0 then
      local k = st % 4
      if k == 0 then dx = 1 elseif k == 1 then dy = 1 elseif k == 2 then dx = -1 else dy = -1 end
    end
    return {dx = dx, dy = dy, state = nxt}
  end
  local ex = h[1].x - mx
  local ey = h[1].y - my
  local sdx = 0
  local sdy = 0
  if ex > 0 then sdx = 1 elseif ex < 0 then sdx = -1 end
  if ey > 0 then sdy = 1 elseif ey < 0 then sdy = -1 end
  local misled = false
  if n >= 3 then
    local a = h[n - 2]
    local b = h[n - 1]
    local sx = b.x - a.x
    local sy = b.y - a.y
    local ux = px - b.x
    local uy = py - b.y
    if (sx ~= 0 or sy ~= 0) and ux == -sx and uy == -sy then misled = true end
  end
  local dx = 0
  local dy = 0
  if (not misled) and ((st % 4) ~= 3) and (sdx ~= 0 or sdy ~= 0) then
    local function gap(ddx, ddy)
      local qx = mx + ddx - px
      local qy = my + ddy - py
      if qx < 0 then qx = -qx end
      if qy < 0 then qy = -qy end
      if qx > qy then return qx end
      return qy
    end
    if gap(sdx, sdy) >= near then
      dx = sdx
      dy = sdy
    elseif sdx ~= 0 and gap(sdx, 0) >= near then
      dx = sdx
    elseif sdy ~= 0 and gap(0, sdy) >= near then
      dy = sdy
    else
      local pdx = 0
      local pdy = 0
      if ax >= ay then
        if sdy ~= 0 then pdy = sdy else pdy = 1 end
      else
        if sdx ~= 0 then pdx = sdx else pdx = 1 end
      end
      if gap(pdx, pdy) < near then
        pdx = -pdx
        pdy = -pdy
      end
      if gap(pdx, pdy) >= near then
        dx = pdx
        dy = pdy
      end
    end
  end
  if mx + dx == px and my + dy == py then
    dx = 0
    dy = 0
  end
  return {dx = dx, dy = dy, state = nxt}
end
