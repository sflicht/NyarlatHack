return function(c)
  local h=c.history
  local n=#h
  local mx=c.mx
  local my=c.my
  local s=c.state
  if s<0 then s=0 end
  if s>1000000 then s=0 end
  local ns=s+1
  if ns>1000000 then ns=0 end
  if n<1 then return {dx=0,dy=0,state=ns} end
  local phase=s%4
  local newest=h[n]
  local ox=h[1].x
  local oy=h[1].y
  local ax=newest.x-mx
  local ay=newest.y-my
  if ax<0 then ax=-ax end
  if ay<0 then ay=-ay end
  local near=ax<=2 and ay<=2
  local dx=0
  local dy=0
  if near or n<4 then
    local sx=newest.x-mx
    local sy=newest.y-my
    if phase%2==0 then
      if sx>0 then dx=-1 elseif sx<0 then dx=1 elseif sy>0 then dy=-1 elseif sy<0 then dy=1 else dx=1 end
    else
      if sy>0 then dy=-1 elseif sy<0 then dy=1 elseif sx>0 then dx=-1 elseif sx<0 then dx=1 else dy=1 end
    end
  elseif phase==3 then
    dx=0
    dy=0
  else
    local vx=0
    local vy=0
    if n>=2 then
      vx=h[2].x-ox
      vy=h[2].y-oy
      if vx>0 then vx=1 elseif vx<0 then vx=-1 end
      if vy>0 then vy=1 elseif vy<0 then vy=-1 end
    end
    local rx=newest.x-h[n-1].x
    local ry=newest.y-h[n-1].y
    if rx>0 then rx=1 elseif rx<0 then rx=-1 end
    if ry>0 then ry=1 elseif ry<0 then ry=-1 end
    local reversed=n>=3 and rx==-vx and ry==-vy and (rx~=0 or ry~=0)
    if reversed then
      if phase%2==0 then
        dx=vx
        if dx==0 then dy=vy end
      else
        dy=vy
        if dy==0 then dx=vx end
      end
      if dx==0 and dy==0 then dx=1 end
    else
      local tx=ox-mx
      local ty=oy-my
      if phase%2==0 then
        if tx>0 then dx=1 elseif tx<0 then dx=-1 elseif ty>0 then dy=1 elseif ty<0 then dy=-1 else dx=vx if dx==0 then dy=vy end end
      else
        if ty>0 then dy=1 elseif ty<0 then dy=-1 elseif tx>0 then dx=1 elseif tx<0 then dx=-1 else dy=vy if dy==0 then dx=vx end end
      end
      if dx==0 and dy==0 then
        if vx~=0 then dx=vx elseif vy~=0 then dy=vy else dx=1 end
      end
    end
  end
  if dx>1 then dx=1 elseif dx<-1 then dx=-1 end
  if dy>1 then dy=1 elseif dy<-1 then dy=-1 end
  return {dx=dx,dy=dy,state=ns}
end
