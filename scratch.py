--model espnetv2 --s 2.0 --dataset city --data-path ./vision_datasets/cityscapes/ --batch-size 25 --crop-size 512 256 --model dicenet --s 1.75 --lr 0.009 --scheduler hybrid --clr-max 61 --epochs 100
evaluate(args, model, image_list, device=device)
